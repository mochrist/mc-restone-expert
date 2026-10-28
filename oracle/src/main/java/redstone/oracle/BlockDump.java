package redstone.oracle;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.SupportType;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Dumps static per-state block data (redstone conductor, sturdy faces, push reaction, ...) for every registered
 * block to a compact JSON file; consumed by {@code src/redstone/sim/blockdata.py}.
 *
 * <p>Format: {@code {"version", "faces", "keys", "blocks": {id: {"props": {name: [values]}, "default": i,
 * "v": {key: value | [value per state]}}}}}. States are indexed in mixed radix over {@code props} in the listed
 * order, the first property being the most significant digit. A key whose value is the same for all states of
 * a block is stored as a scalar, otherwise as a list with one entry per state index. Face sets are bit masks over
 * {@code faces} (Direction ordinal order). Level-dependent predicates are evaluated in an empty block getter at
 * the origin.
 */
final class BlockDump {
	private static final Direction[] FACES = Direction.values();
	private static final String[] KEYS = {
		"conductor", "signal_source", "analog_output", "sturdy_full", "sturdy_rigid", "sturdy_center", "push",
		"air", "replaceable", "block_entity", "full_collision", "solid", "solid_render", "wire_connect",
		"trapdoor", "unstable_bottom_center", "unbreakable",
	};

	private BlockDump() {
	}

	static int write(Path file) throws IOException {
		JsonObject blocks = new JsonObject();
		int states = 0;
		for (Block block : BuiltInRegistries.BLOCK) {
			blocks.add(BuiltInRegistries.BLOCK.getKey(block).toString(), dumpBlock(block));
			states += block.getStateDefinition().getPossibleStates().size();
		}
		JsonObject root = new JsonObject();
		root.addProperty("version", SharedConstants.getCurrentVersion().name());
		JsonArray faces = new JsonArray();
		for (Direction d : FACES) {
			faces.add(d.getSerializedName());
		}
		root.add("faces", faces);
		JsonArray keys = new JsonArray();
		for (String k : KEYS) {
			keys.add(k);
		}
		root.add("keys", keys);
		root.add("blocks", blocks);
		Path parent = file.toAbsolutePath().getParent();
		if (parent != null) {
			Files.createDirectories(parent);
		}
		Files.writeString(file, new Gson().toJson(root), StandardCharsets.UTF_8);
		return states;
	}

	private static JsonObject dumpBlock(Block block) {
		List<Property<?>> props = new ArrayList<>(block.getStateDefinition().getProperties());
		int[] strides = new int[props.size()];
		int count = 1;
		for (int i = props.size() - 1; i >= 0; i--) {
			strides[i] = count;
			count *= props.get(i).getPossibleValues().size();
		}
		JsonObject propsJson = new JsonObject();
		for (Property<?> p : props) {
			JsonArray values = new JsonArray();
			for (String v : valueNames(p)) {
				values.add(v);
			}
			propsJson.add(p.getName(), values);
		}

		JsonElement[][] table = new JsonElement[KEYS.length][count];
		for (BlockState state : block.getStateDefinition().getPossibleStates()) {
			int index = index(state, props, strides);
			Map<String, JsonElement> values = evaluate(state);
			for (int k = 0; k < KEYS.length; k++) {
				table[k][index] = Objects.requireNonNull(values.get(KEYS[k]), KEYS[k]);
			}
		}

		JsonObject v = new JsonObject();
		for (int k = 0; k < KEYS.length; k++) {
			JsonElement first = table[k][0];
			boolean uniform = true;
			for (JsonElement e : table[k]) {
				uniform &= e.equals(first);
			}
			if (uniform) {
				v.add(KEYS[k], first);
			} else {
				JsonArray arr = new JsonArray();
				for (JsonElement e : table[k]) {
					arr.add(e);
				}
				v.add(KEYS[k], arr);
			}
		}
		JsonObject out = new JsonObject();
		if (!props.isEmpty()) {
			out.add("props", propsJson);
			out.addProperty("default", index(block.defaultBlockState(), props, strides));
		}
		out.add("v", v);
		return out;
	}

	private static Map<String, JsonElement> evaluate(BlockState s) {
		EmptyBlockGetter level = EmptyBlockGetter.INSTANCE;
		BlockPos pos = BlockPos.ZERO;
		Map<String, JsonElement> m = new LinkedHashMap<>();
		m.put("conductor", new JsonPrimitive(s.isRedstoneConductor(level, pos)));
		m.put("signal_source", new JsonPrimitive(s.isSignalSource()));
		m.put("analog_output", new JsonPrimitive(s.hasAnalogOutputSignal()));
		m.put("sturdy_full", new JsonPrimitive(sturdyMask(s, SupportType.FULL)));
		m.put("sturdy_rigid", new JsonPrimitive(sturdyMask(s, SupportType.RIGID)));
		m.put("sturdy_center", new JsonPrimitive(sturdyMask(s, SupportType.CENTER)));
		m.put("push", new JsonPrimitive(s.getPistonPushReaction().name().toLowerCase(Locale.ROOT)));
		m.put("air", new JsonPrimitive(s.isAir()));
		m.put("replaceable", new JsonPrimitive(s.canBeReplaced()));
		m.put("block_entity", new JsonPrimitive(s.hasBlockEntity()));
		m.put("full_collision", new JsonPrimitive(s.isCollisionShapeFullBlock(level, pos)));
		m.put("solid", new JsonPrimitive(s.isSolid()));
		m.put("solid_render", new JsonPrimitive(s.isSolidRender()));
		// shouldRedstoneWireConnectTo(level, pos, direction): bits 0-5 per Direction ordinal, bit 6 for null.
		int wire = 0;
		for (Direction d : FACES) {
			if (s.shouldRedstoneWireConnectTo(level, pos, d)) {
				wire |= 1 << d.ordinal();
			}
		}
		if (s.shouldRedstoneWireConnectTo(level, pos, null)) {
			wire |= 1 << 6;
		}
		m.put("wire_connect", new JsonPrimitive(wire));
		m.put("trapdoor", new JsonPrimitive(s.getBlock() instanceof TrapDoorBlock));
		m.put("unstable_bottom_center", new JsonPrimitive(s.is(BlockTags.UNSTABLE_BOTTOM_CENTER)));
		// PistonBaseBlock.isPushable refuses blocks with destroy speed -1 (bedrock, barrier, command blocks, ...).
		m.put("unbreakable", new JsonPrimitive(s.getDestroySpeed(level, pos) == -1.0F));
		return m;
	}

	private static int sturdyMask(BlockState s, SupportType type) {
		int mask = 0;
		for (Direction d : FACES) {
			if (s.isFaceSturdy(EmptyBlockGetter.INSTANCE, BlockPos.ZERO, d, type)) {
				mask |= 1 << d.ordinal();
			}
		}
		return mask;
	}

	private static int index(BlockState state, List<Property<?>> props, int[] strides) {
		int index = 0;
		for (int i = 0; i < props.size(); i++) {
			Property<?> p = props.get(i);
			index += strides[i] * p.getPossibleValues().indexOf(state.getValue(p));
		}
		return index;
	}

	private static <T extends Comparable<T>> List<String> valueNames(Property<T> p) {
		List<String> names = new ArrayList<>();
		for (T value : p.getPossibleValues()) {
			names.add(p.getName(value));
		}
		return names;
	}
}
