# -*- coding: utf-8 -*-
"""Rectangular shelf packing for roll materials, with fixed obstacle support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PieceDemand:
    key: str
    width: float
    height: float
    meta: dict = field(default_factory=dict)


@dataclass
class Obstacle:
    x: float
    y: float
    width: float
    height: float
    gap_group: str = ''


@dataclass
class Placement:
    key: str
    x: float
    y: float
    width: float
    height: float
    rotated: bool
    meta: dict = field(default_factory=dict)


@dataclass
class RollResult:
    width: float
    used_length: float
    placements: List[Placement] = field(default_factory=list)
    obstacles: List[Obstacle] = field(default_factory=list)


def _overlaps(ax, ay, aw, ah, bx, by, bw, bh, gap: float = 0.0) -> bool:
    return not (
        ax + aw + gap <= bx
        or bx + bw + gap <= ax
        or ay + ah + gap <= by
        or by + bh + gap <= ay
    )


class NestingEngine:
    """Shelf / skyline-ish packer on a fixed-width roll (width = cross axis).

    gap: 一般圖間距（同膜）。
    gap_diff_group: 膜屬性不同時的圖間距；0 表示不啟用差異間距。
    圖塊透過 meta['gap_group']（例如冷裱屬性值）分組。
    """

    def __init__(
        self,
        roll_width: float,
        gap: float = 5.0,
        margin: float = 0.0,
        allow_rotate: bool = True,
        gap_diff_group: float = 0.0,
    ):
        self.roll_width = float(roll_width)
        self.gap = float(gap or 0.0)
        self.gap_diff_group = float(gap_diff_group or 0.0)
        self.margin = float(margin or 0.0)
        self.allow_rotate = bool(allow_rotate)
        self.usable_width = self.roll_width - 2 * self.margin

    def _group_of_meta(self, meta: Optional[dict]) -> str:
        if not meta:
            return ''
        return str(meta.get('gap_group') or '')

    def _gap_for(self, group_a: str, group_b: str) -> float:
        ga = group_a or ''
        gb = group_b or ''
        if self.gap_diff_group > self.gap and ga != gb:
            return self.gap_diff_group
        return self.gap

    def _orientations(
        self,
        w: float,
        h: float,
        force_rotation: Optional[int] = None,
    ) -> List[Tuple[float, float, bool]]:
        """回傳 (cross_w, along_h, rotated_bool)。

        force_rotation: 0/90/180/270 時只允許對應朝向（印刷池手動旋轉）。
        """
        if force_rotation is not None:
            rot = int(force_rotation) % 360
            if rot in (90, 270):
                opts = [(h, w, True)]
            else:
                opts = [(w, h, False)]
        else:
            opts = [(w, h, False)]
            if self.allow_rotate and abs(w - h) > 1e-6:
                opts.append((h, w, True))
        # Prefer orientation that fits and has smaller cross-width first for denser shelves
        opts = [o for o in opts if o[0] <= self.usable_width + 1e-6]
        opts.sort(key=lambda o: (o[0], o[1]))
        return opts

    def _collides(
        self,
        x, y, w, h,
        occupied: List[Tuple[float, float, float, float, str]],
        demand_group: str,
    ) -> bool:
        for ox, oy, ow, oh, og in occupied:
            gap = self._gap_for(demand_group, og)
            if _overlaps(x, y, w, h, ox, oy, ow, oh, gap):
                return True
        return False

    def pack(
        self,
        demands: List[PieceDemand],
        seed_rolls: Optional[List[RollResult]] = None,
    ) -> Tuple[List[RollResult], List[PieceDemand]]:
        """
        Pack demands onto rolls. seed_rolls may already contain obstacles (locked pieces).
        Returns (rolls, unplaced_demands).
        """
        rolls: List[RollResult] = []
        if seed_rolls:
            for seed in seed_rolls:
                rolls.append(
                    RollResult(
                        width=seed.width or self.roll_width,
                        used_length=seed.used_length,
                        placements=list(seed.placements),
                        obstacles=list(seed.obstacles),
                    )
                )
        if not rolls:
            rolls.append(RollResult(width=self.roll_width, used_length=0.0))

        # Larger first tends to leave fewer awkward gaps
        ordered = sorted(
            demands,
            key=lambda d: max(d.width, d.height) * min(d.width, d.height),
            reverse=True,
        )
        unplaced: List[PieceDemand] = []

        for demand in ordered:
            force_rot = None
            if demand.meta and demand.meta.get('force_rotation') is not None:
                try:
                    force_rot = int(demand.meta.get('force_rotation')) % 360
                except (TypeError, ValueError):
                    force_rot = None
            orients = self._orientations(
                demand.width, demand.height, force_rotation=force_rot,
            )
            if not orients:
                unplaced.append(demand)
                continue

            demand_group = self._group_of_meta(demand.meta)
            placed = False
            for roll in rolls:
                occupied = [
                    (o.x, o.y, o.width, o.height, o.gap_group or '')
                    for o in roll.obstacles
                ] + [
                    (
                        p.x, p.y, p.width, p.height,
                        self._group_of_meta(p.meta),
                    )
                    for p in roll.placements
                ]
                max_y = max(
                    [self.margin]
                    + [o.y + o.height for o in roll.obstacles]
                    + [p.y + p.height for p in roll.placements]
                )

                # Candidate y：依與各已占塊的間距規則推候選線
                y_candidates = {self.margin}
                if occupied:
                    y_candidates.add(max_y + self.gap)
                    # 與任一已占塊若屬異膜，也要準備大間距候選
                    if self.gap_diff_group > self.gap:
                        y_candidates.add(max_y + self.gap_diff_group)
                for ox, oy, ow, oh, og in occupied:
                    y_candidates.add(oy)
                    y_candidates.add(oy + oh + self._gap_for(demand_group, og))
                for y in sorted(y_candidates):
                    for pw, ph, rotated in orients:
                        # Scan x along usable width
                        x = self.margin
                        while x + pw <= self.roll_width - self.margin + 1e-6:
                            if not self._collides(x, y, pw, ph, occupied, demand_group):
                                roll.placements.append(
                                    Placement(
                                        key=demand.key,
                                        x=x,
                                        y=y,
                                        width=pw,
                                        height=ph,
                                        rotated=rotated,
                                        meta=dict(demand.meta),
                                    )
                                )
                                roll.used_length = max(
                                    roll.used_length,
                                    y + ph + self.margin,
                                )
                                placed = True
                                break
                            # advance x past colliding rect using pairwise gap
                            next_x = x + self.gap + 1.0
                            for ox, oy, ow, oh, og in occupied:
                                gap = self._gap_for(demand_group, og)
                                if _overlaps(x, y, pw, ph, ox, oy, ow, oh, gap):
                                    next_x = max(next_x, ox + ow + gap)
                            if next_x <= x:
                                next_x = x + self.gap + 1.0
                            x = next_x
                        if placed:
                            break
                    if placed:
                        break
                if placed:
                    break

            if not placed:
                # New roll
                new_roll = RollResult(width=self.roll_width, used_length=0.0)
                pw, ph, rotated = orients[0]
                new_roll.placements.append(
                    Placement(
                        key=demand.key,
                        x=self.margin,
                        y=self.margin,
                        width=pw,
                        height=ph,
                        rotated=rotated,
                        meta=dict(demand.meta),
                    )
                )
                new_roll.used_length = self.margin + ph + self.margin
                rolls.append(new_roll)

        # Drop empty new rolls that somehow have nothing (keep those with obstacles)
        final_rolls = [
            r for r in rolls if r.placements or r.obstacles
        ] or rolls[:1]
        return final_rolls, unplaced

    @staticmethod
    def utilization(roll_width: float, used_length: float, placements: List[Placement]) -> float:
        if not used_length or not roll_width:
            return 0.0
        area = sum(p.width * p.height for p in placements)
        return round(100.0 * area / (roll_width * used_length), 2)
