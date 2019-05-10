""" Helper functions for calculating 2D and 3D bounding box IoU.

Collected by Charles R. Qi
Date: September 2017
"""
from __future__ import print_function

import tensorflow as tf
import numpy as np
from scipy.spatial import ConvexHull
from avod.core import box_8c_encoder
from avod.core import oriented_nms


def polygon_clip(subjectPolygon, clipPolygon):
    """ Clip a polygon with another polygon.

   Ref: https://rosettacode.org/wiki/Sutherland-Hodgman_polygon_clipping#Python

   Args:
     subjectPolygon: a list of (x,y) 2d points, any polygon.
     clipPolygon: a list of (x,y) 2d points, has to be *convex*
   Note:
     **points have to be counter-clockwise ordered**

   Return:
     a list of (x,y) vertex point for the intersection polygon.
   """

    def inside(p):
        return (cp2[0] - cp1[0]) * (p[1] - cp1[1]) > (cp2[1] - cp1[1]) * (p[0] - cp1[0])

    def computeIntersection():
        dc = [cp1[0] - cp2[0], cp1[1] - cp2[1]]
        dp = [s[0] - e[0], s[1] - e[1]]
        n1 = cp1[0] * cp2[1] - cp1[1] * cp2[0]
        n2 = s[0] * e[1] - s[1] * e[0]
        n3 = 1.0 / (dc[0] * dp[1] - dc[1] * dp[0])
        return [(n1 * dp[0] - n2 * dc[0]) * n3, (n1 * dp[1] - n2 * dc[1]) * n3]

    outputList = subjectPolygon
    cp1 = clipPolygon[-1]

    for clipVertex in clipPolygon:
        cp2 = clipVertex
        inputList = outputList
        outputList = []
        s = inputList[-1]

        for subjectVertex in inputList:
            e = subjectVertex
            if inside(e):
                if not inside(s):
                    outputList.append(computeIntersection())
                outputList.append(e)
            elif inside(s):
                outputList.append(computeIntersection())
            s = e
        cp1 = cp2
        if len(outputList) == 0:
            return None
    return outputList


def convex_hull_intersection(p1, p2):
    """ Compute area of two convex hull's intersection area.
        p1,p2 are a list of (x,y) tuples of hull vertices.
        return a list of (x,y) for the intersection and its volume
    """
    inter_p = polygon_clip(p1, p2)
    if inter_p is not None:
        hull_inter = ConvexHull(inter_p)
        return inter_p, hull_inter.volume
    else:
        return None, 0.0


def polygon_area(x, y):
    """ Ref: http://stackoverflow.com/questions/24467972/calculate-area-of-polygon-given-x-y-coordinates """
    return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def polygon_iou(rect1, rect2):
    area1 = polygon_area(np.array(rect1)[:, 0], np.array(rect1)[:, 1])
    area2 = polygon_area(np.array(rect2)[:, 0], np.array(rect2)[:, 1])
    inter, inter_area = convex_hull_intersection(rect1, rect2)
    iou_2d = inter_area / (area1 + area2 - inter_area)
    return iou_2d, inter_area


def box3d_vol(corners):
    """ corners: (8,3) no assumption on axis direction """
    a = np.sqrt(np.sum((corners[0, :] - corners[1, :]) ** 2))
    b = np.sqrt(np.sum((corners[1, :] - corners[2, :]) ** 2))
    c = np.sqrt(np.sum((corners[0, :] - corners[4, :]) ** 2))
    return a * b * c


def is_clockwise(p):
    x = p[:, 0]
    y = p[:, 1]
    return np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)) > 0


def box3d_iou(corners1, corners2):
    """ Compute 3D bounding box IoU. for Oriented BBox

    Input:
        corners1: numpy array (8,3), assume up direction is negative Y
        corners2: numpy array (8,3), assume up direction is negative Y
    Output:
        iou: 3D bounding box IoU
        iou_2d: bird's eye view 2D bounding box IoU

    todo (rqi): add more description on corner points' orders.
    """
    # corner points are in counter clockwise order
    rect1 = [(corners1[i, 0], corners1[i, 2]) for i in range(3, -1, -1)]
    rect2 = [(corners2[i, 0], corners2[i, 2]) for i in range(3, -1, -1)]
    # iou_2d, inter_area = polygon_iou(rect1, rect2)
    iou_2d, inter_area = oriented_nms.polygon_iou(rect1, rect2)
    ymax = min(corners1[0, 1], corners2[0, 1])
    ymin = max(corners1[4, 1], corners2[4, 1])
    inter_vol = inter_area * max(0.0, ymax - ymin)
    vol1 = box3d_vol(corners1)
    vol2 = box3d_vol(corners2)
    iou = inter_vol / (vol1 + vol2 - inter_vol)
    return iou, iou_2d


def compute_recall_iou(
    pred_boxes_3d, label_boxes_3d, label_cls, proposal_gt_iou2d, proposal_gt_iou3d
):
    """
    Input:
        pred_boxes_3d: (n,7) [x,y,z,l,w,h,ry]
        label_boxes_3d: (m,7) [x,y,z,l,w,h,ry]
        label_cls: (m) [cls]
        propoal_gt_iou2d: (n,m) 2d iou between proposal and ground truth
        propoal_gt_iou3d: (n,m) 3d iou between proposal and ground truth
    Output:
        recall_50: (1)
        recall_70: (1)
        iou2ds: (n), max bev oriented 2d IoU among label GTs
        iou3ds: (n), max 3d IoU among label GTs
        iou3ds_gt_boxes: (n,7), corresponding GT box3d
        iou3ds_gt_cls: (n), corresponding GT cls
    """
    n = pred_boxes_3d.shape[0]
    m = label_boxes_3d.shape[0]
    mx_iou2ds = proposal_gt_iou2d[:, :m]
    mx_iou3ds = proposal_gt_iou3d[:, :m]
    iou2ds = np.zeros((n), dtype=np.float32)
    iou3ds = np.zeros((n), dtype=np.float32)
    iou3ds_gt_boxes = np.zeros((n, 7), dtype=np.float32)
    iou3ds_gt_cls = np.zeros((n), dtype=np.float32)

    if m * n > 0:
        recall_50 = np.sum(np.max(mx_iou3ds, axis=0) > 0.5)
        recall_70 = np.sum(np.max(mx_iou3ds, axis=0) > 0.7)
        iou2ds = np.max(mx_iou2ds, axis=1)
        iou3ds = np.max(mx_iou3ds, axis=1)
        iou3ds_gt_boxes = label_boxes_3d[np.argmax(mx_iou3ds, axis=1)]
        iou3ds_gt_cls = label_cls[np.argmax(mx_iou3ds, axis=1)]

    return (
        recall_50,
        recall_70,
        iou2ds,
        iou3ds,
        iou3ds_gt_boxes,
        iou3ds_gt_cls,
        mx_iou3ds,
    )


def get_iou(bb1, bb2):
    """
    Calculate the Intersection over Union (IoU) of two 2D bounding boxes. for Axis-Aligned BBox

    Parameters
    ----------
    bb1 : dict
        Keys: {'x1', 'x2', 'y1', 'y2'}
        The (x1, y1) position is at the top left corner,
        the (x2, y2) position is at the bottom right corner
    bb2 : dict
        Keys: {'x1', 'x2', 'y1', 'y2'}
        The (x, y) position is at the top left corner,
        the (x2, y2) position is at the bottom right corner

    Returns
    -------
    float
        in [0, 1]
    """
    assert bb1["x1"] < bb1["x2"]
    assert bb1["y1"] < bb1["y2"]
    assert bb2["x1"] < bb2["x2"]
    assert bb2["y1"] < bb2["y2"]

    # determine the coordinates of the intersection rectangle
    x_left = max(bb1["x1"], bb2["x1"])
    y_top = max(bb1["y1"], bb2["y1"])
    x_right = min(bb1["x2"], bb2["x2"])
    y_bottom = min(bb1["y2"], bb2["y2"])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    # The intersection of two axis-aligned bounding boxes is always an
    # axis-aligned bounding box
    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # compute the area of both AABBs
    bb1_area = (bb1["x2"] - bb1["x1"]) * (bb1["y2"] - bb1["y1"])
    bb2_area = (bb2["x2"] - bb2["x1"]) * (bb2["y2"] - bb2["y1"])

    # compute the intersection over union by taking the intersection
    # area and dividing it by the sum of prediction + ground-truth
    # areas - the interesection area
    iou = intersection_area / float(bb1_area + bb2_area - intersection_area)
    assert iou >= 0.0
    assert iou <= 1.0
    return iou


def box2d_iou(box1, box2):
    """ Compute 2D bounding box IoU. for Axis-Aligned BBox

    Input:
        box1: tuple of (xmin,ymin,xmax,ymax)
        box2: tuple of (xmin,ymin,xmax,ymax)
    Output:
        iou: 2D IoU scalar
    """
    return get_iou(
        {"x1": box1[0], "y1": box1[1], "x2": box1[2], "y2": box1[3]},
        {"x1": box2[0], "y1": box2[1], "x2": box2[2], "y2": box2[3]},
    )


if __name__ == "__main__":
    """
    # Function for polygon ploting
    import matplotlib
    from matplotlib.patches import Polygon
    from matplotlib.collections import PatchCollection
    import matplotlib.pyplot as plt
    def plot_polys(plist,scale=500.0):
        fig, ax = plt.subplots()
        patches = []
        for p in plist:
            poly = Polygon(np.array(p)/scale, True)
            patches.append(poly)

    pc = PatchCollection(patches, cmap=matplotlib.cm.jet, alpha=0.5)
    colors = 100*np.random.rand(len(patches))
    pc.set_array(np.array(colors))
    ax.add_collection(pc)
    plt.show()
 
    # Demo on ConvexHull
    points = np.random.rand(30, 2)   # 30 random points in 2-D
    hull = ConvexHull(points)
    # **In 2D "volume" is is area, "area" is perimeter
    print(('Hull area: ', hull.volume))
    for simplex in hull.simplices:
        print(simplex)

    # Demo on convex hull overlaps
    sub_poly = [(0,0),(300,0),(300,300),(0,300)]
    clip_poly = [(150,150),(300,300),(150,450),(0,300)]
    inter_poly = polygon_clip(sub_poly, clip_poly)
    print(polygon_area(np.array(inter_poly)[:,0], np.array(inter_poly)[:,1]))
    
    # Test convex hull interaction function
    rect1 = [(50,0),(50,300),(300,300),(300,0)]
    rect2 = [(150,150),(300,300),(150,450),(0,300)]
    plot_polys([rect1, rect2])
    inter, area = convex_hull_intersection(rect1, rect2)
    print((inter, area))
    if inter is not None:
        print(polygon_area(np.array(inter)[:,0], np.array(inter)[:,1]))
    
    print('------------------')
    rect1 = [(0.30026005199835404, 8.9408694211408424), \
             (-1.1571105364358421, 9.4686676477075533), \
             (0.1777082043006144, 13.154404877812102), \
             (1.6350787927348105, 12.626606651245391)]
    rect1 = [rect1[0], rect1[3], rect1[2], rect1[1]]
    rect2 = [(0.23908745901608636, 8.8551095691132886), \
             (-1.2771419487733995, 9.4269062966181956), \
             (0.13138836963152717, 13.161896351296868), \
             (1.647617777421013, 12.590099623791961)]
    rect2 = [rect2[0], rect2[3], rect2[2], rect2[1]]
    plot_polys([rect1, rect2])
    inter, area = convex_hull_intersection(rect1, rect2)
    print((inter, area))
    """

    """
    import timeit

    rect1 = [(1, 1), (0, 1), (0, 0), (1, 0)]
    rect2 = [(1.25, 2.25), (0.25, 1.25), (1.25, 0.25), (2.25, 1.25)]
    print(timeit.timeit("polygon_iou(rect1, rect2)", number=10000, globals=globals()))
    print(
        timeit.timeit(
            "oriented_nms.polygon_iou(rect1, rect2)",
            number=10000,
            setup="from avod.core import oriented_nms",
            globals=globals(),
        )
    )
    """
    pred_boxes_3d = np.asarray([[0.5, 0.5, 0.5, 1, 1, 1, 0]])
    label_boxes_3d = np.asarray([[1, 1, 1, 1, 1, 1, 0]])
    # label_cls = np.asarray([1])
    # print(pred_boxes_3d.shape)
    # print(label_boxes_3d.shape)
    # ans = compute_recall_iou_old(pred_boxes_3d, label_boxes_3d, label_cls)
    # print(ans)

    from compute_iou import box3d_iou_tf

    pred_boxes_3d = tf.convert_to_tensor(pred_boxes_3d, dtype=tf.float32)
    label_boxes_3d = tf.convert_to_tensor(label_boxes_3d, dtype=tf.float32)

    iou3d, iou2d = box3d_iou_tf(label_boxes_3d, pred_boxes_3d)

    with tf.Session() as sess:
        iou3d, iou2d = sess.run([iou3d, iou2d])
    print("iou2d: ", iou2d)
    print("iou3d: ", iou3d)
