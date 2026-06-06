"""algorithm 层公开 API。"""

from algorithm.encode import encode, encode_image
from algorithm.evaluation import EERResult, compute_eer, pairwise_scores, plot_roc
from algorithm.matcher import match_best, match_distance
from algorithm.preprocess import preprocess
from algorithm.template import PalmTemplate, make_template

__all__ = [
    "PalmTemplate",
    "make_template",
    "preprocess",
    "encode",
    "encode_image",
    "match_distance",
    "match_best",
    "pairwise_scores",
    "compute_eer",
    "EERResult",
    "plot_roc",
]
