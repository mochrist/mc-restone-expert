package redstone.oracle;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** A compiled scenario (docs/scenario-format.md, section 3). */
public record Scenario(
		String name,
		int[] size,
		List<Block> blocks,
		List<BlockEntity> blockEntities,
		int ticks,
		List<Input> inputs,
		List<Probe> probes) {

	public static final int FORMAT = 1;

	public record Block(int[] pos, String state) {}

	public record BlockEntity(int[] pos, String snbt) {}

	public record Input(int tick, int[] pos, String action, String state) {}

	public record Probe(String name, int[] pos) {}

	public static Scenario load(Path path) throws IOException {
		JsonObject o = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8)).getAsJsonObject();
		int format = o.get("format").getAsInt();
		if (format != FORMAT) {
			throw new IllegalArgumentException("unsupported scenario format " + format);
		}
		List<Block> blocks = new ArrayList<>();
		for (JsonElement e : array(o, "blocks")) {
			JsonObject b = e.getAsJsonObject();
			blocks.add(new Block(pos(b.get("pos")), b.get("state").getAsString()));
		}
		List<BlockEntity> blockEntities = new ArrayList<>();
		for (JsonElement e : array(o, "block_entities")) {
			JsonObject b = e.getAsJsonObject();
			blockEntities.add(new BlockEntity(pos(b.get("pos")), b.get("snbt").getAsString()));
		}
		List<Input> inputs = new ArrayList<>();
		for (JsonElement e : array(o, "inputs")) {
			JsonObject i = e.getAsJsonObject();
			String action = i.get("action").getAsString();
			if (!action.equals("use") && !action.equals("setblock")) {
				throw new IllegalArgumentException("unknown action " + action);
			}
			String state = i.has("state") ? i.get("state").getAsString() : null;
			if (action.equals("setblock") && state == null) {
				throw new IllegalArgumentException("setblock needs a state");
			}
			inputs.add(new Input(i.get("tick").getAsInt(), pos(i.get("pos")), action, state));
		}
		List<Probe> probes = new ArrayList<>();
		for (JsonElement e : array(o, "probes")) {
			JsonObject p = e.getAsJsonObject();
			probes.add(new Probe(p.get("name").getAsString(), pos(p.get("pos"))));
		}
		return new Scenario(o.get("name").getAsString(), pos(o.get("size")), blocks, blockEntities,
				o.get("ticks").getAsInt(), inputs, probes);
	}

	private static JsonArray array(JsonObject o, String key) {
		return o.has(key) ? o.getAsJsonArray(key) : new JsonArray();
	}

	private static int[] pos(JsonElement e) {
		JsonArray a = e.getAsJsonArray();
		if (a.size() != 3) {
			throw new IllegalArgumentException("position needs 3 coordinates: " + a);
		}
		return new int[] {a.get(0).getAsInt(), a.get(1).getAsInt(), a.get(2).getAsInt()};
	}
}
