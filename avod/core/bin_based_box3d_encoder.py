"""
This module converts data to and from the 'box_3d' format
 [x, y, z, l, w, h, ry]
"""
import tensorflow as tf

from wavedata.tools.obj_detection import obj_utils


def tf_decode(
    ref_pts,
    ref_theta,
    bin_x,
    res_x_norm,
    bin_z,
    res_z_norm,
    bin_theta,
    res_theta_norm,
    res_y,
    res_size,
    mean_sizes,
    S,
    DELTA,
    R,
    DELTA_THETA,
):
    """Turns bin-based box3d format into an box_3d

    Input:
        ref_pts: (B,p,3) [x,y,z]
        ref_theta: (B,p) [ry] or a constant value
        
        bin_x: (B,p), bin assignments along X-axis
        res_x_norm: (B,p), normalized residual corresponds to bin_x
        bin_z: (B,p), bin assignments along Z-axis
        res_z_norm: (B,p), normalized residual corresponds to bin_z
        bin_theta: (B,p), bin assignments for orientation
        res_theta_norm: (B,p), normalized residual corresponds to bin_theta
        res_y: (B,p), residual w.r.t. ref_pts along Y-axis
        res_size: (B,p,3), residual w.r.t. the average object size [l,w,h]

        mean_sizes, (B,p,3), average object size [l,w,h]
        S: XZ search range [-S, +S]
        DELTA: XZ_BIN_LEN
        R: THETA search range [-R, +R]
        DELTA_THETA: THETA_BIN_LEN = 2 * R / NUM_BIN_THETA
    
    Output:
        boxes_3d: (B,p,7) 3D box in box_3d format [x, y, z, l, w, h, ry]
    """
    ndims = ref_pts.shape.ndims
    if ndims == 3:
        x = (
            ref_pts[:, :, 0]
            + (tf.to_float(bin_x) + 0.5) * DELTA
            - S
            + res_x_norm * 0.5 * DELTA
        )
        z = (
            ref_pts[:, :, 2]
            + (tf.to_float(bin_z) + 0.5) * DELTA
            - S
            + res_z_norm * 0.5 * DELTA
        )
        y = ref_pts[:, :, 1] + res_y
    elif ndims == 2:
        x = (
            ref_pts[:, 0]
            + (tf.to_float(bin_x) + 0.5) * DELTA
            - S
            + res_x_norm * 0.5 * DELTA
        )
        z = (
            ref_pts[:, 2]
            + (tf.to_float(bin_z) + 0.5) * DELTA
            - S
            + res_z_norm * 0.5 * DELTA
        )
        y = ref_pts[:, 1] + res_y
    theta = (
        ref_theta
        + (tf.to_float(bin_theta) + 0.5) * DELTA_THETA
        - R
        + res_theta_norm * 0.5 * DELTA_THETA
    )
    size = mean_sizes + res_size

    if ndims == 3:
        l = size[:, :, 0]
        w = size[:, :, 1]
        h = size[:, :, 2]
        # combine all
        boxes_3d = tf.stack([x, y, z, l, w, h, theta], axis=2)
    elif ndims == 2:
        l = size[:, 0]
        w = size[:, 1]
        h = size[:, 2]
        # combine all
        boxes_3d = tf.stack([x, y, z, l, w, h, theta], axis=1)

    return boxes_3d


def tf_encode(ref_pts, ref_theta, boxes_3d, mean_sizes, S, DELTA, R, DELTA_THETA):
    """Turns box_3d into bin-based box3d format
    Input:
        ref_pts: (B,p,3) [x,y,z]
        ref_theta: (B,p) [ry] or a constant value
        boxes_3d: (B,p,7) 3D box in box_3d format [x, y, z, l, w, h, ry]
        
        mean_sizes, (B,p,3), average object size [l,w,h]
        S: XZ search range [-S, +S]
        DELTA: XZ_BIN_LEN
        R: THETA search range [-R, +R]
        DELTA_THETA: THETA_BIN_LEN = 2 * R / NUM_BIN_THETA
    
    Output:
        bin_x: (B,p), bin assignments along X-axis
        res_x_norm: (B,p), normalized residual corresponds to bin_x
        bin_z: (B,p), bin assignments along Z-axis
        res_z_norm: (B,p), normalized residual corresponds to bin_z
        bin_theta: (B,p), bin assignments for orientation
        res_theta_norm: (B,p), normalized residual corresponds to bin_theta
        res_y: (B,p), residual w.r.t. ref_pts along Y-axis
        res_size: (B,p,3), residual w.r.t. the average object size [l,w,h]
    """
    ndims = ref_pts.shape.ndims
    if ndims == 3:
        dx = boxes_3d[:, :, 0] - ref_pts[:, :, 0]
        dy = boxes_3d[:, :, 1] - ref_pts[:, :, 1]
        dz = boxes_3d[:, :, 2] - ref_pts[:, :, 2]
        dsize = boxes_3d[:, :, 3:6] - mean_sizes
        dtheta = boxes_3d[:, :, 6] - ref_theta
    elif ndims == 2:
        dx = boxes_3d[:, 0] - ref_pts[:, 0]
        dy = boxes_3d[:, 1] - ref_pts[:, 1]
        dz = boxes_3d[:, 2] - ref_pts[:, 2]
        dsize = boxes_3d[:, 3:6] - mean_sizes
        dtheta = boxes_3d[:, 6] - ref_theta

    bin_x = tf.floor((dx + S) / DELTA)
    res_x_norm = (dx + S - (bin_x + 0.5) * DELTA) / (0.5 * DELTA)

    bin_z = tf.floor((dz + S) / DELTA)
    res_z_norm = (dz + S - (bin_z + 0.5) * DELTA) / (0.5 * DELTA)

    bin_theta = tf.floor((dtheta + R) / DELTA_THETA)
    res_theta_norm = (dtheta + R - (bin_theta + 0.5) * DELTA_THETA) / (
        0.5 * DELTA_THETA
    )

    res_y = dy
    res_size = dsize

    return (
        bin_x,
        res_x_norm,
        bin_z,
        res_z_norm,
        bin_theta,
        res_theta_norm,
        res_y,
        res_size,
    )
