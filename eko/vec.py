"""Small 3D helpers. Vectors are (x, y, z) tuples."""

import math


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    mag = length(a)
    if mag <= 1e-8:
        return None
    return (a[0] / mag, a[1] / mag, a[2] / mag)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rotate_y(v, yaw_rad):
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    return (c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2])


def rotate_euler(v, pitch, yaw, roll):
    """Rotate v by pitch (X), yaw (Y), roll (Z), in degrees, applied Y then X then Z."""
    p, y, r = math.radians(pitch), math.radians(yaw), math.radians(roll)
    x, yy, z = rotate_y(v, y)
    c, s = math.cos(p), math.sin(p)
    yy, z = c * yy - s * z, s * yy + c * z
    c, s = math.cos(r), math.sin(r)
    x, yy = c * x - s * yy, s * x + c * yy
    return (x, yy, z)


def euler_matrix(pitch, yaw, roll):
    """Rows of the rotation matrix that maps local vectors into the world."""
    ex = rotate_euler((1.0, 0.0, 0.0), pitch, yaw, roll)
    ey = rotate_euler((0.0, 1.0, 0.0), pitch, yaw, roll)
    ez = rotate_euler((0.0, 0.0, 1.0), pitch, yaw, roll)
    return [list(ex), list(ey), list(ez)]


def dist(a, b):
    return length(sub(a, b))
