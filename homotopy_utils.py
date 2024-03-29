"""
Functions for computing h-signatures of paths through the environment.
Based on this paper: https://www.roboticsproceedings.org/rss07/p02.pdf
"""
from typing import Dict, List

import hjson
import numpy as np
from multiset import Multiset
from numpy.linalg import norm

NO_HOMOTOPY = Multiset([-999])


def squared_norm(x, **kwargs):
    return np.sum(np.square(x), axis=-1, **kwargs)


def get_h_signature(path, skeletons: Dict):
    """
    Computes the h-signature of a path, given the skeletons of the obstacles.

    Args:
        path: A path through the environment, as a list of points in 3D.
        skeletons:  A dictionary of skeletons, where the keys are the names of the obstacles and the values are the
            skeletons of the obstacles.

    Returns:

    """
    # Densely discretize the path so that we can integrate the field along it
    path_discretized = discretize_path(path)
    path_deltas = np.diff(path_discretized, axis=0)
    hs = []
    for skeleton in skeletons.values():
        bs = skeleton_field_dir(skeleton, path_discretized[:-1])
        # Integrate the field along the path
        h = np.sum(np.sum(bs * path_deltas, axis=-1), axis=0)
        # round to nearest integer since the output should really either be 0 or 1
        # absolute value because we don't care which "direction" the loop goes through an obstacle
        h = abs(int(h.round(0)))
        hs.append(h)
    return tuple(hs)


def skeleton_field_dir(skeleton, r):
    """
    Computes the field direction at the input points, where the conductor is the skeleton of an obstacle.
    A skeleton is defined by a set of points in 3D, like a line-strip, and can represent only a genus-1 obstacle (donut)
    Assumes μ and I are 1.
    Based on this paper: https://www.roboticsproceedings.org/rss07/p02.pdf

    Variables in my code <--> math in the paper:

        s_prev = s_i^j
        s_next = s_i^j'
        p_prev = p
        p_next = p'

    Args:
        skeleton: [n, 3] the points that define the skeleton
        r: [b, 3] the points at which to compute the field.
    """
    if not np.all(skeleton[0] == skeleton[-1]):
        raise ValueError("Skeleton must be a closed loop! Add the first point to the end.")

    s_prev = skeleton[:-1][None]  # [1, n, 3]
    s_next = skeleton[1:][None]  # [1, n, 3]

    p_prev = s_prev - r[:, None]  # [b, n, 3]
    p_next = s_next - r[:, None]  # [b, n, 3]
    squared_segment_lens = squared_norm(s_next - s_prev, keepdims=True)
    d = np.cross((s_next - s_prev), np.cross(p_next, p_prev)) / squared_segment_lens  # [b, n, 3]

    # bs is a matrix [b, n,3] where each bs[i, j] corresponds to a line segment in the skeleton
    squared_d_lens = squared_norm(d, keepdims=True)
    p_next_lens = norm(p_next, axis=-1, keepdims=True) + 1e-6
    p_prev_lens = norm(p_prev, axis=-1, keepdims=True) + 1e-6

    # Epsilon is added to the denominator to avoid dividing by zero, which would happen for points _on_ the skeleton.
    ε = 1e-6
    d_scale = np.where(squared_d_lens > ε, 1 / (squared_d_lens + ε), 0)

    bs = d_scale * (np.cross(d, p_next) / p_next_lens - np.cross(d, p_prev) / p_prev_lens)

    b = bs.sum(axis=1) / (4 * np.pi)
    return b


def discretize_path(path: np.ndarray, n=1000):
    """ densely resamples a path to one containing n points """
    num_points = path.shape[0]
    t = np.linspace(0, 1, num_points)
    t_new = np.linspace(0, 1, n)
    path_discretized = np.zeros((n, 3))

    for i in range(3):
        path_discretized[:, i] = np.interp(t_new, t, path[:, i])

    return path_discretized


def load_skeletons(skeleton_filename):
    with open(skeleton_filename, 'r') as f:
        skeletons = hjson.load(f)
    return {k: np.array(v) for k, v in skeletons.items()}


def passes_through(graph, i, j):
    for k in graph.nodes:
        if k == i or k == j:
            continue
        if k == 'b' or i == 'b' or j == 'b':
            continue
        i_loc = graph.nodes[i]['loc']
        j_loc = graph.nodes[j]['loc']
        k_loc = graph.nodes[k]['loc']
        lower = min(i_loc, j_loc)
        upper = max(i_loc, j_loc)
        if lower < k_loc < upper:
            return True
    return False


def check_new_cycle(cycle, valid_cycles):
    for valid_cycle in valid_cycles:
        if set(cycle) == set(valid_cycle):
            return False
    return True


def floorify(xpos):
    xpos = xpos.copy()
    xpos[2] = -0.8
    return xpos


def has_gripper_gripper_edge(loop):
    # pairwise ( + ) is a way to iterate over a list in pairs but ensure we loop back around
    for e1, e2 in pairwise(loop + loop[0:1]):
        if 'g' in e1 and 'g' in e2:
            return e1, e2
    return None


def pairwise(x):
    return zip(x[:-1], x[1:])


def from_to(i, j):
    """ Inclusive of both i and j """
    if i < j:
        return range(i + 1, j + 1)
    else:
        return range(i, j, -1)


def make_h_desired(skeletons: Dict, goal_skel_names: List[str]):
    h_desired = [0] * len(skeletons)
    for n in goal_skel_names:
        goal_skel_i = get_goal_skel_i(skeletons, n)
        h_desired[goal_skel_i] = 1
    h_desired = Multiset([tuple(h_desired)])
    return h_desired


def get_goal_skel_i(skeletons, goal_skel_name):
    return list(skeletons.keys()).index(goal_skel_name)


def h2array(h: Multiset):
    h_list = []
    for h_i in h:
        h_list.extend(list(h_i))
    return np.array(h_list)
