# import cv2
import numpy as np
import os

from PIL import Image

from wavedata.tools.obj_detection import obj_utils

from avod.core import box_3d_encoder
from avod.core import box_8c_encoder

class LabelSegPreprocessor(object):
    def __init__(self,
                 dataset,
                 label_seg_dir,
                 expand_gt_size):
        """Preprocesses label segs and saves to files for RPN-seg training

        Args:
            dataset: Dataset object
            label_seg_dir: directory to save the info
        """

        self._dataset = dataset
        self.label_seg_utils = self._dataset.kitti_utils.label_seg_utils

        self._label_seg_dir = label_seg_dir

        self._expand_gt_size = expand_gt_size

    def preprocess(self, indices):
        """Preprocesses label seg info and saves info to files

        Args:
            indices (int array): sample indices to process.
                If None, processes all samples
        """
        # Get anchor stride for class
        expand_gt_size = self._expand_gt_size

        dataset = self._dataset
        dataset_utils = self._dataset.kitti_utils
        classes_name = dataset.classes_name

        # Make folder if it doesn't exist yet
        output_dir = self.label_seg_utils.get_file_path(classes_name,
                                                         expand_gt_size,
                                                         sample_name=None)
        os.makedirs(output_dir, exist_ok=True)

        # Load indices of data_split
        all_samples = dataset.sample_list

        if indices is None:
            indices = np.arange(len(all_samples))
        num_samples = len(indices)

        # For each image in the dataset, save info on the anchors
        for sample_idx in indices:
            # Get image name for given cluster
            sample_name = all_samples[sample_idx].name
            img_idx = int(sample_name)

            # Check for existing files and skip to the next
            if self._check_for_existing(classes_name, expand_gt_size,
                                        sample_name):
                print("{} / {}: Sample already preprocessed".format(
                    sample_idx + 1, num_samples, sample_name))
                continue

            # Get ground truth and filter based on difficulty
            obj_labels = obj_utils.read_labels(dataset.label_dir, img_idx)

            # Filter objects to dataset classes
            obj_labels = dataset_utils.filter_labels(obj_labels)

            image = Image.open(dataset.get_rgb_image_path(sample_name))
            image_shape = [image.size[1], image.size[0]]
            point_cloud = dataset_utils.get_point_cloud(dataset.pc_source,
                                                           img_idx,
                                                           image_shape)
            point_cloud = point_cloud.T
            # Filtering by class has no valid ground truth, skip this image
            if len(obj_labels) == 0:
                print("{} / {} No {}s for sample {} "
                      "(Ground Truth Filter)".format(
                          sample_idx + 1, num_samples,
                          classes_name, sample_name))
                label_seg = np.zeros((point_cloud.shape[0]), dtype=int)
                self._save_to_file(classes_name, expand_gt_size,
                                   sample_name, label_seg)
                continue
            
            label_boxes_3d = [
                 box_3d_encoder.object_label_to_box_3d(obj_label)
                 for obj_label in obj_labels]
            for box_3d in label_boxes_3d:
                box_3d[3:6] += expand_gt_size
            label_boxes_8co = np.asarray(
                [box_8c_encoder.np_box_3d_to_box_8co(box_3d).T
                 for box_3d in label_boxes_3d])

            label_classes = [
                dataset_utils.class_str_to_index(obj_label.type)
                for obj_label in obj_labels]
            label_classes = np.asarray(label_classes, dtype=np.int32)

            label_seg = self.label_seg_utils.label_point_cloud(
                                    point_cloud, 
                                    label_boxes_8co, 
                                    label_classes)
            foreground_points = label_seg[label_seg > 0]
            print("{} / {}:"
                  "{:>6} foreground points, "
                  "for {:>3} {}(s) for sample {}".format(
                      sample_idx + 1, num_samples,
                      len(foreground_points),
                      len(obj_labels), classes_name, sample_name
                  ))

            # Save label segs
            self._save_to_file(classes_name, expand_gt_size,
                               sample_name, label_seg)
    
    def _check_for_existing(self, classes_name, expand_gt_size, sample_name):
        """
        Checks if a label seg file exists already

        Args:
            classes_name (str): classes name, e.g. 'Car', 'Pedestrian',
                'Cyclist', 'People'
            sample_name (str): sample name from dataset, e.g. '000123'

        Returns:
            True if the label seg file already exists
        """

        file_name = self.label_seg_utils.get_file_path(classes_name, 
                                                       expand_gt_size, 
                                                       sample_name)
        if os.path.exists(file_name):
            return True

        return False

    def _save_to_file(self, classes_name, expand_gt_size, sample_name,
                      label_seg=np.array([])):
        """
        Saves the label seg info to a file

        Args:
            classes_name (str): classes name, e.g. 'Car', 'Pedestrian',
                'Cyclist', 'People'
            sample_name (str): name of sample, e.g. '000123'
            label_seg: ndarray of label seg of shape (N)
                defaults to an empty array
        """

        file_name = self.label_seg_utils.get_file_path(classes_name,
                                                        expand_gt_size,
                                                        sample_name)

        # Save to npy file
        label_seg = np.asarray(label_seg, dtype=np.int32)
        np.save(file_name, label_seg)
