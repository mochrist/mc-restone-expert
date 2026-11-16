package redstone.oracle;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import net.fabricmc.fabric.api.entity.FakePlayer;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.SectionPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.ComparatorBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.storage.ServerLevelData;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Executes one scenario following docs/scenario-format.md, section 2.
 *
 * <p>The game is frozen. Each game tick is a single {@code /tick step 1}; the protocol continues in the
 * server-tick-end callback once the step was consumed, so inputs and sampling happen between two game
 * ticks like real player actions.
 */
final class ScenarioRun {
	private static final Logger LOG = LoggerFactory.getLogger("rsx-oracle");
	private static final String P = "[rsx-oracle] ";

	/** Default min corner of every scenario; chunk aligned, high above the flat world surface. A scenario may
	 * name its own ("origin"); system properties rsx.originX/Y/Z move the default. */
	static final BlockPos ORIGIN = new BlockPos(Integer.getInteger("rsx.originX", 0),
			Integer.getInteger("rsx.originY", 200), Integer.getInteger("rsx.originZ", 0));
	/** Air margin cleared around the circuit before each run. */
	static final int MARGIN = 16;
	/**
	 * Placement flags: UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE as specified, plus UPDATE_SUPPRESS_DROPS,
	 * UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS and UPDATE_SKIP_ON_PLACE (= vanilla {@code /setblock ... strict}),
	 * so that neither onPlace (e.g. dust/diode neighbor updates) nor removal side effects run.
	 */
	static final int PLACE_FLAGS = Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE | Block.UPDATE_SUPPRESS_DROPS
			| Block.UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS | Block.UPDATE_SKIP_ON_PLACE;
	private static final int MAX_WAIT_TICKS = 200;
	/** Server ticks the chunks must stay block-ticking before the scenario is built. */
	private static final int SETTLE_TICKS = 5;

	private enum Phase { LOADING_CHUNKS, STEPPING, DONE }

	private final MinecraftServer server;
	private final ServerLevel level;
	private final Scenario scenario;
	private final Path out;
	private final BoundingBox area;
	private final BlockPos origin;
	private final Map<String, List<Object[]>> samples = new LinkedHashMap<>();
	private final List<Long> deltas = new ArrayList<>();
	private Phase phase = Phase.LOADING_CHUNKS;
	private int t;
	private long stepFrom;
	private int waited;
	private int settled;

	ScenarioRun(MinecraftServer server, ServerLevel level, Scenario scenario, Path out) {
		this.server = server;
		this.level = level;
		this.scenario = scenario;
		this.out = out;
		int[] s = scenario.size();
		int[] o = scenario.origin();
		this.origin = o != null ? new BlockPos(o[0], o[1], o[2]) : ORIGIN;
		this.area = new BoundingBox(
				origin.getX() - MARGIN, origin.getY() - MARGIN, origin.getZ() - MARGIN,
				origin.getX() + s[0] - 1 + MARGIN, origin.getY() + s[1] - 1 + MARGIN, origin.getZ() + s[2] - 1 + MARGIN);
		if (area.minY() < level.getMinY() || area.maxY() >= level.getMaxY()) {
			throw new IllegalArgumentException("scenario does not fit the world height at y=" + origin.getY());
		}
	}

	boolean isDone() {
		return phase == Phase.DONE;
	}

	void start() {
		forEachChunk((cx, cz) -> level.setChunkForced(cx, cz, true));
		LOG.info(P + "{}: {} blocks, {} ticks, {} inputs, {} probes", scenario.name(), scenario.blocks().size(),
				scenario.ticks(), scenario.inputs().size(), scenario.probes().size());
	}

	/** Called at the end of every server tick. */
	void onEndTick() throws IOException {
		switch (phase) {
			case LOADING_CHUNKS -> {
				if (!chunksReady()) {
					settled = 0;
					waitOrFail("chunks to load");
					return;
				}
				// Let the chunk tickets settle for a few server ticks (cold start of the server) before building.
				if (++settled < SETTLE_TICKS) {
					return;
				}
				build();
				phase = Phase.STEPPING;
				t = 0;
				protocolStep();
			}
			case STEPPING -> {
				long now = level.getGameTime();
				if (now == stepFrom) {
					waitOrFail("the tick step to run");
					return;
				}
				if (!chunksReady()) {
					// A scheduled tick in a chunk that is not block-ticking is silently postponed by the game.
					throw new IllegalStateException("tick " + t + ": scenario chunks stopped ticking");
				}
				long delta = now - stepFrom;
				deltas.add(delta);
				if (delta != 1) {
					throw new IllegalStateException("tick " + t + ": game time advanced by " + delta + " instead of 1");
				}
				t++;
				protocolStep();
			}
			case DONE -> { }
		}
	}

	/** Abort: stop stepping so the next scenario starts from a frozen game. */
	void abort() {
		server.tickRateManager().stopStepping();
		phase = Phase.DONE;
	}

	private void waitOrFail(String what) {
		if (++waited > MAX_WAIT_TICKS) {
			throw new IllegalStateException("timed out waiting for " + what);
		}
	}

	/** Steps 2.1-2.3 for the current tick t. */
	private void protocolStep() throws IOException {
		waited = 0;
		for (Scenario.Input input : scenario.inputs()) {
			if (input.tick() == t) {
				apply(input);
			}
		}
		for (Scenario.Probe probe : scenario.probes()) {
			List<Object[]> points = samples.computeIfAbsent(probe.name(), k -> new ArrayList<>());
			String value = sample(at(probe.pos()));
			if (points.isEmpty() || !points.getLast()[1].equals(value)) {
				points.add(new Object[] {t, value});
			}
		}
		if (t < scenario.ticks()) {
			stepFrom = level.getGameTime();
			if (!server.tickRateManager().stepGameIfPaused(1)) {
				throw new IllegalStateException("game is not frozen");
			}
		} else {
			writeTrace();
			phase = Phase.DONE;
		}
	}

	private void build() {
		var blocks = level.holderLookup(Registries.BLOCK);
		// Clear region + margin to air without updates, then place every block exactly.
		BlockState air = Blocks.AIR.defaultBlockState();
		for (BlockPos pos : BlockPos.betweenClosed(area.minX(), area.minY(), area.minZ(), area.maxX(), area.maxY(), area.maxZ())) {
			if (level.getBlockEntity(pos) != null) {
				level.removeBlockEntity(pos);
			}
			level.setBlock(pos, air, PLACE_FLAGS);
		}
		clearScheduledTicks();
		// Entities (dropped items, falling blocks, ...) of the previous scenario would trigger sculk sensors etc.
		AABB box = new AABB(area.minX(), area.minY(), area.minZ(), area.maxX() + 1, area.maxY() + 1, area.maxZ() + 1);
		for (Entity entity : level.getEntities((Entity) null, box, e -> !(e instanceof Player))) {
			entity.discard();
		}
		for (Scenario.Block b : scenario.blocks()) {
			level.setBlock(at(b.pos()), parseState(blocks, b.state()), PLACE_FLAGS);
		}
		for (Scenario.BlockEntity be : scenario.blockEntities()) {
			BlockPos pos = at(be.pos());
			BlockEntity entity = level.getBlockEntity(pos);
			if (entity == null) {
				throw new IllegalArgumentException("no block entity at " + List.of(be.pos()[0], be.pos()[1], be.pos()[2]));
			}
			CompoundTag tag;
			try {
				tag = TagParser.parseCompoundFully(be.snbt());
			} catch (CommandSyntaxException e) {
				throw new IllegalArgumentException("bad SNBT at " + pos + ": " + e.getMessage(), e);
			}
			entity.loadWithComponents(TagValueInput.create(ProblemReporter.DISCARDING, level.registryAccess(), tag));
			entity.setChanged();
		}
		clearScheduledTicks();
		// Deterministic phase: the game time carries over between scenarios and the daylight detector samples at
		// gameTime % 20 == 0, so move the clock forward to the scenario's phase. Jumping forward (never back) by
		// more than the torch burnout window keeps recent-toggle bookkeeping of earlier scenarios expired.
		// The world clock is frozen (advance_time off); the weather is cleared.
		long phase = Math.floorMod(scenario.gameTime(), 20L);
		long target = level.getGameTime() + 100;
		target += Math.floorMod(phase - target, 20L);
		((ServerLevelData) level.getLevelData()).setGameTime(target);
		server.setWeatherParameters(0, 0, false, false);
		LOG.info(P + "{}: built at {}, game time {}", scenario.name(), origin.toShortString(), level.getGameTime());
	}

	private void clearScheduledTicks() {
		level.getBlockTicks().clearArea(area);
		level.getFluidTicks().clearArea(area);
	}

	private void apply(Scenario.Input input) {
		BlockPos pos = at(input.pos());
		switch (input.action()) {
			case "use" -> {
				FakePlayer player = FakePlayer.get(level);
				BlockHitResult hit = new BlockHitResult(Vec3.atCenterOf(pos), Direction.UP, pos, false);
				var result = level.getBlockState(pos).useWithoutItem(level, player, hit);
				LOG.info(P + "{}: tick {} use {} -> {}", scenario.name(), t, pos.toShortString(), result);
			}
			case "setblock" -> {
				level.setBlock(pos, parseState(level.holderLookup(Registries.BLOCK), input.state()), Block.UPDATE_ALL);
				LOG.info(P + "{}: tick {} setblock {} {}", scenario.name(), t, pos.toShortString(), input.state());
			}
			default -> throw new IllegalArgumentException("unknown action " + input.action());
		}
	}

	private String sample(BlockPos pos) {
		String value = stateString(level.getBlockState(pos));
		if (level.getBlockEntity(pos) instanceof ComparatorBlockEntity comparator) {
			value += "|output=" + comparator.getOutputSignal();
		}
		return value;
	}

	/** {@code namespace:id[key=value,...]} with properties sorted by key; no brackets without properties. */
	static String stateString(BlockState state) {
		StringBuilder sb = new StringBuilder(BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString());
		List<Property<?>> props = new ArrayList<>(state.getProperties());
		if (!props.isEmpty()) {
			props.sort(Comparator.comparing(Property::getName));
			sb.append('[');
			for (int i = 0; i < props.size(); i++) {
				if (i > 0) {
					sb.append(',');
				}
				sb.append(props.get(i).getName()).append('=').append(valueName(state, props.get(i)));
			}
			sb.append(']');
		}
		return sb.toString();
	}

	private static <T extends Comparable<T>> String valueName(BlockState state, Property<T> property) {
		return property.getName(state.getValue(property));
	}

	private static BlockState parseState(net.minecraft.core.HolderLookup<Block> blocks, String state) {
		try {
			return BlockStateParser.parseForBlock(blocks, state, false).blockState();
		} catch (CommandSyntaxException e) {
			throw new IllegalArgumentException("bad block state " + state + ": " + e.getMessage(), e);
		}
	}

	private void writeTrace() throws IOException {
		JsonObject o = new JsonObject();
		o.addProperty("format", 1);
		o.addProperty("scenario", scenario.name());
		o.addProperty("source", "oracle");
		o.addProperty("version", server.getServerVersion());
		o.addProperty("ticks", scenario.ticks());
		JsonObject probes = new JsonObject();
		for (Scenario.Probe p : scenario.probes()) {
			JsonArray a = new JsonArray();
			for (int c : p.pos()) {
				a.add(c);
			}
			probes.add(p.name(), a);
		}
		o.add("probes", probes);
		JsonObject s = new JsonObject();
		for (var e : samples.entrySet()) {
			JsonArray points = new JsonArray();
			for (Object[] point : e.getValue()) {
				JsonArray pt = new JsonArray();
				pt.add((Integer) point[0]);
				pt.add((String) point[1]);
				points.add(pt);
			}
			s.add(e.getKey(), points);
		}
		o.add("samples", s);
		Files.createDirectories(out.getParent());
		Files.writeString(out, new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(o) + "\n",
				StandardCharsets.UTF_8);
		boolean allOne = deltas.stream().allMatch(d -> d == 1);
		LOG.info(P + "{}: done, {} steps, game time deltas all 1: {} -> {}", scenario.name(), deltas.size(), allOne, out);
	}

	private BlockPos at(int[] p) {
		return origin.offset(p[0], p[1], p[2]);
	}

	private boolean chunksReady() {
		boolean[] ok = {true};
		forEachChunk((cx, cz) -> ok[0] &= level.hasChunk(cx, cz) && level.shouldTickBlocksAt(ChunkPos.pack(cx, cz)));
		return ok[0];
	}

	private void forEachChunk(ChunkVisitor v) {
		for (int cx = SectionPos.blockToSectionCoord(area.minX()); cx <= SectionPos.blockToSectionCoord(area.maxX()); cx++) {
			for (int cz = SectionPos.blockToSectionCoord(area.minZ()); cz <= SectionPos.blockToSectionCoord(area.maxZ()); cz++) {
				v.visit(cx, cz);
			}
		}
	}

	@FunctionalInterface
	private interface ChunkVisitor {
		void visit(int cx, int cz);
	}
}
