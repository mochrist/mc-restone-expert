package redstone.oracle;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.gamerules.GameRules;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.stream.Stream;

/**
 * Server-side oracle: runs every {@code <rsx.in>/*.scenario.json} and writes {@code <rsx.out>/<name>.trace.json}.
 *
 * <p>System properties: {@code rsx.in} (default {@code <run>/rsx/in}), {@code rsx.out} (default
 * {@code <run>/rsx/out}), {@code rsx.exitWhenDone} (stop the server after the last scenario).
 * Input files are deleted once processed; a failing scenario writes {@code <name>.error.txt} instead of a trace.
 */
public class OracleMod implements ModInitializer {
	private static final Logger LOG = LoggerFactory.getLogger("rsx-oracle");
	private static final String P = "[rsx-oracle] ";
	private static final String SUFFIX = ".scenario.json";

	private final Deque<Path> queue = new ArrayDeque<>();
	private boolean started;
	private Path in;
	private Path out;
	private ScenarioRun current;
	private Path currentFile;
	private int ok;
	private int failed;

	@Override
	public void onInitialize() {
		ServerLifecycleEvents.SERVER_STARTED.register(this::onStarted);
		ServerTickEvents.END_SERVER_TICK.register(this::onEndTick);
	}

	private void onStarted(MinecraftServer server) {
		Path run = server.getServerDirectory();
		in = Path.of(System.getProperty("rsx.in", run.resolve("rsx/in").toString())).toAbsolutePath();
		out = Path.of(System.getProperty("rsx.out", run.resolve("rsx/out").toString())).toAbsolutePath();
		GameRules rules = server.getGameRules();
		rules.set(GameRules.RANDOM_TICK_SPEED, 0, server);
		rules.set(GameRules.SPAWN_MOBS, false, server);
		rules.set(GameRules.ADVANCE_WEATHER, false, server);
		rules.set(GameRules.ADVANCE_TIME, false, server);
		server.tickRateManager().setFrozen(true);
		// Real time between server ticks only; game ticks are driven one at a time by stepping.
		server.tickRateManager().setTickRate(Float.parseFloat(System.getProperty("rsx.tickRate", "200")));
		try {
			Files.createDirectories(in);
			Files.createDirectories(out);
			try (Stream<Path> files = Files.list(in)) {
				files.filter(p -> p.getFileName().toString().endsWith(SUFFIX)).sorted().forEach(queue::add);
			}
		} catch (IOException e) {
			LOG.error(P + "cannot read input dir {}", in, e);
		}
		LOG.info(P + "{} scenario(s) in {}", queue.size(), in);
		started = true;
	}

	private void onEndTick(MinecraftServer server) {
		if (!started) {
			return;
		}
		try {
			if (current == null) {
				if (!nextScenario(server)) {
					return;
				}
			}
			current.onEndTick();
			if (current.isDone()) {
				ok++;
				finishFile();
			}
		} catch (Exception e) {
			failed++;
			LOG.error(P + "scenario {} failed", currentFile, e);
			if (current != null) {
				current.abort();
			}
			writeError(e);
			finishFile();
		}
	}

	/** Starts the next queued scenario; returns false (and maybe stops the server) when none is left. */
	private boolean nextScenario(MinecraftServer server) {
		while (current == null) {
			currentFile = queue.poll();
			if (currentFile == null) {
				started = false;
				LOG.info(P + "all scenarios done: {} ok, {} failed", ok, failed);
				if (Boolean.getBoolean("rsx.exitWhenDone")) {
					LOG.info(P + "stopping server");
					server.halt(false);
				}
				return false;
			}
			try {
				Scenario scenario = Scenario.load(currentFile);
				ServerLevel level = server.overworld();
				current = new ScenarioRun(server, level, scenario, out.resolve(scenario.name() + ".trace.json"));
				current.start();
			} catch (Exception e) {
				failed++;
				LOG.error(P + "cannot start {}", currentFile, e);
				writeError(e);
				finishFile();
			}
		}
		return true;
	}

	private void finishFile() {
		try {
			Files.deleteIfExists(currentFile);
		} catch (IOException e) {
			LOG.warn(P + "cannot delete {}", currentFile, e);
		}
		current = null;
		currentFile = null;
	}

	private void writeError(Exception e) {
		String name = currentFile.getFileName().toString();
		name = name.substring(0, name.length() - SUFFIX.length());
		StringWriter sw = new StringWriter();
		e.printStackTrace(new PrintWriter(sw));
		try {
			Files.writeString(out.resolve(name + ".error.txt"), sw.toString(), StandardCharsets.UTF_8);
		} catch (IOException io) {
			LOG.error(P + "cannot write error file", io);
		}
	}
}
