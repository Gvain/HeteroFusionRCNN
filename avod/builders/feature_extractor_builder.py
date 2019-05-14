from avod.core.feature_extractors.pointcnn import PointCNN
from avod.core.feature_extractors.bev_vgg_pyramid import BevVggPyr

from avod.core.feature_extractors.img_vgg import ImgVgg
from avod.core.feature_extractors.img_vgg_pyramid import ImgVggPyr

from avod.core.feature_extractors.pointnet import PointNet


def get_extractor(extractor_config):

    extractor_type = extractor_config.WhichOneof("feature_extractor")

    # BEV feature extractors
    if extractor_type == "pc_pointcnn":
        return PointCNN(extractor_config.pc_pointcnn)
    elif extractor_type == "bev_vgg_pyr":
        return BevVggPyr(extractor_config.bev_vgg_pyr)
    elif extractor_type == "pc_pointnet":
        return PointNet(extractor_config.pc_pointnet)

    # Image feature extractors
    elif extractor_type == "img_vgg":
        return ImgVgg(extractor_config.img_vgg)
    elif extractor_type == "img_vgg_pyr":
        return ImgVggPyr(extractor_config.img_vgg_pyr)

    return ValueError("Invalid feature extractor type", extractor_type)
