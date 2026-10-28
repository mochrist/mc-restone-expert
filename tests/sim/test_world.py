"""Unit tests of the simulator core against behaviour read from the 26.3 code."""

from redstone.model import BlockState, Pos
from redstone.sim import World
from redstone.sim.block import REGISTRY, Block
from redstone.sim.constants import TickPriority


class Recorder(Block):
    def __init__(self, name, log):
        super().__init__(name)
        self.log = log

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        self.log.append(("nc", pos))

    def tick(self, world, pos, state):
        self.log.append(("tick", pos, world.game_time))


def _world_with_recorders(positions):
    log = []
    rec = Recorder("test:rec", log)
    REGISTRY.register(rec, "test:rec")
    w = World()
    for p in positions:
        w.blocks[p] = BlockState.parse("test:rec")
    return w, rec, log


def test_update_neighbors_order_is_w_e_d_u_n_s():
    c = Pos(5, 5, 5)
    ns = [c.offset(d) for d in __import__("redstone.sim.world", fromlist=["UPDATE_ORDER"]).UPDATE_ORDER]
    w, rec, log = _world_with_recorders(ns)
    w.update_neighbors_at(c, rec)
    assert [p for _, p in log] == ns


def test_ticks_ordered_by_time_priority_then_insertion():
    a, b, c = Pos(0, 0, 0), Pos(1, 0, 0), Pos(2, 0, 0)
    w, rec, log = _world_with_recorders([a, b, c])
    w.schedule_tick(a, rec, 2, TickPriority.NORMAL)
    w.schedule_tick(b, rec, 2, TickPriority.HIGH)
    w.schedule_tick(c, rec, 1, TickPriority.NORMAL)
    w.schedule_tick(a, rec, 1, TickPriority.EXTREMELY_HIGH)  # duplicate (pos, block): ignored
    w.tick()
    w.tick()
    assert log == [("tick", c, 1), ("tick", b, 2), ("tick", a, 2)]


def test_neighbor_updates_are_depth_first():
    """A block that updates its neighbours while being updated: those run before the remaining siblings."""
    log = []

    class Chain(Block):
        def neighbor_changed(self, world, pos, state, source, moved_by_piston):
            log.append(pos)
            if pos == Pos(1, 0, 0):  # first neighbour (west of 2,0,0 is 1,0,0)
                world.update_neighbors_at(pos, self)

    chain = REGISTRY.register(Chain("test:chain"), "test:chain")
    w = World()
    for p in [Pos(1, 0, 0), Pos(3, 0, 0), Pos(0, 0, 0)]:
        w.blocks[p] = BlockState.parse("test:chain")
    w.update_neighbors_at(Pos(2, 0, 0), chain)
    # (1,0,0) is updated first; its own neighbour (0,0,0) runs before (3,0,0)
    assert log == [Pos(1, 0, 0), Pos(0, 0, 0), Pos(3, 0, 0)]
