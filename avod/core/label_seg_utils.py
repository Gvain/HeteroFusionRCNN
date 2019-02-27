import os

import numpy as np
import tensorflow as tf

import avod

from avod.core.label_seg_preprocessor import LabelSegPreprocessor
from avod.core import box_8c_encoder
from wavedata.tools.obj_detection import obj_utils


class LabelSegUtils:
    def __init__(self, dataset):

        self._dataset = dataset

        ##############################
        # Parse KittiUtils config
        ##############################
        self.kitti_utils_config = dataset.config.kitti_utils_config
        self._area_extents = self.kitti_utils_config.area_extents

        ##############################
        # Parse MiniBatchUtils config
        ##############################
        self.config = self.kitti_utils_config.label_seg_config
        self._expand_gt_size = self.config.expand_gt_size

        # Setup paths
        self.label_seg_dir = avod.root_dir() + '/data/label_segs/' + \
            dataset.name + '/' + dataset.cluster_split + '/' + \
            dataset.pc_source

    def preprocess_rpn_label_segs(self, indices):
        """Generates rpn mini batch info for the kitti dataset

            Preprocesses data and saves data to files.
            Each file contains information that is used to feed
            to the network for RPN training.
        """
        label_seg_preprocessor = \
            LabelSegPreprocessor(self._dataset,
                                  self.label_seg_dir,
                                  self._expand_gt_size)

        label_seg_preprocessor.preprocess(indices)
        
    def get_label_seg(self, classes_name, expand_gt_size, sample_name):
        """Reads in the file containing the information matrix

        Args:
            classes_name: object type, one of ('Car', 'Pedestrian',
                'Cyclist', 'People')
            sample_name: image name to read the corresponding file

        Returns:
            label_seg: [class_idx, box_idx]
                (e.g. 0 or 1, for "Background" or "Car")

            [] if the file contains an empty array
        """
        file_name = self.get_file_path(classes_name, expand_gt_size,
                                       sample_name)

        if not os.path.exists(file_name):
            raise FileNotFoundError(
                "{} not found for sample {} in {}, "
                "run the preprocessing script first".format(
                    file_name,
                    sample_name,
                    self.label_seg_dir))

        label_seg = np.load(file_name)
        return label_seg

    def get_file_path(self, classes_name, expand_gt_size, sample_name):
        """Gets the full file path to the anchors info

        Args:
            classes_name: name of classes ('Car', 'Pedestrian', 'Cyclist',
                'People')
            sample_name: sample name, e.g. '000123'

        Returns:
            The label seg file path. Returns the folder if
                sample_name is None
        """

        expand_gt_size = np.round(expand_gt_size, 3)
        if sample_name:
            return self.label_seg_dir + '/' + classes_name + \
                '[ ' + str(expand_gt_size) + ']/' + \
                sample_name + ".npy"

        return self.label_seg_dir + '/' + classes_name + \
            '[ ' + str(expand_gt_size) + ']'
    
    @classmethod 
    def label_point_cloud_v2(cls, points, boxes_8co, boxes_3d, klasses):
        '''
        Give all points a label if it is inside a box
         Input:
           points: (N x 3)
           boxes_8co: (M x 8 x 3)
           boxes_3d: (M x 7) [x,y,z,l,w,h,ry]
           klasses: (M) [klass] 1-based, 0-background
         Return:
           label_seg: (N x 8), [klass,x,y,z,l,w,h,ry] 
        '''
        num_points = points.shape[0]
        num_boxes = boxes_8co.shape[0]
        label_seg = np.zeros((num_points, 8), dtype=np.float32)
        for i in range(num_boxes):
            klass = klasses[i]
            box_8co = boxes_8co[i,:,:]
            box_3d = boxes_3d[i]
            point_mask = obj_utils.is_point_inside(points.T, box_8co.T)
            for j in range(num_points):
                if point_mask[j]:
                    label_seg[j, 0] = float(klass)
                    label_seg[j, 1:8] = box_3d[:]
        return label_seg

    @classmethod 
    def label_point_cloud(cls, points, boxes_8co, boxes_3d, klasses):
        '''
        Give all points a label if it is inside a box
         Input:
           points: (N x 3)
           boxes_8co: (M x 8 x 3)
           boxes_3d: (M x 7) [x,y,z,l,w,h,ry]
           klasses: (M) [klass] 1-based, 0-background
         Return:
           label_seg: (N x 8), [klass,x,y,z,l,w,h,ry] 
        '''
        num_points = points.shape[0]
        num_boxes = boxes_8co.shape[0]
        label_seg = np.zeros((num_points, 8), dtype=np.float32)
        if num_boxes > 0:
            facets = box_8c_encoder.np_box_8co_to_facet(boxes_8co)
        for i in range(num_boxes):
            klass = klasses[i]
            box_8co = boxes_8co[i,:,:]
            box_3d = boxes_3d[i]
            facet = facets[i,:,:]
            x = box_8co[:,0]
            y = box_8co[:,1]
            z = box_8co[:,2]
            max_x = x.max(axis = 0)
            max_y = y.max(axis = 0)
            max_z = z.max(axis = 0)
            min_x = x.min(axis = 0)
            min_y = y.min(axis = 0)
            min_z = z.min(axis = 0)
            
            for j in range(num_points):
                if label_seg[j,0] > 0:
                    continue
                point = points[j,:]
                px, py, pz = point[0], point[1], point[2]
                # return false if point is siginificant away from all vertices
                if px > max_x or px < min_x or \
                   py > max_y or py < min_y or \
                   pz > max_z or pz < min_z:
                    continue
                elif cls.point_inside_facet(point, facet):
                    label_seg[j, 0] = float(klass)
                    label_seg[j, 1:8] = box_3d[:]
        return label_seg
    
    @classmethod
    def point_inside_facet(cls, point, facet):
        '''
        Check if point is inside an convex 3d object defined by facet
         Input:
           point: ([x,y,z])
           facet: (N x [a,b,c,d]) i.e. for a cube, N is 6
         Return:
           boolean
        '''
        for i in range(facet.shape[0]):
            norm = facet[i,0:3]
            A = facet[i,4:]
            D = point - A
            product = np.dot(norm, D)
            if product < 0:
              return False
        return True

def main():
    points = np.asarray([[1.0, 0, 0.1],[-0.3, -0.5, -0.3]])
    boxes_3d = np.asarray([0, 0, 0, 1, 1, 1, 3.14/4])
    boxes_8co = box_8c_encoder.np_box_3d_to_box_8co(boxes_3d).T
    boxes_3d = boxes_3d.reshape(-1, 7)
    boxes_8co = boxes_8co.reshape(-1, 8, 3)
    print(boxes_8co)
    klasses = np.asarray([1])
    label_seg = LabelSegUtils.label_point_cloud(points, boxes_8co, boxes_3d, klasses)
    print(label_seg)
    foreground = label_seg[label_seg[:,0] > 0]
    print(foreground)
    label_seg = LabelSegUtils.label_point_cloud_v2(points, boxes_8co, boxes_3d, klasses)
    print(label_seg)
    foreground = label_seg[label_seg[:,0] > 0]
    print(foreground)

if __name__ == '__main__':
    main()
