"""Main entry point for baseline calculation.
"""

from mica_text_coref.coref.movie_coref import baseline

from absl import app
from absl import flags
import os
import sys

FLAGS = flags.FLAGS
proj_dir = os.getcwd()

def p(path: str) -> str:
    return os.path.join(proj_dir, path)

flags.DEFINE_string("wl_weights", 
    default=p("data/word_level_coref/data/roberta_(e20_2021.05.02_01.16)_release.pt"),
    help="Weights of word-level roberta coreference model")
flags.DEFINE_string("wl_config", default=p("coref/word_level_coref/config.toml"),
    help="Config file of word-level roberta coreference model")
flags.DEFINE_enum("wl_genre", default="wb", enum_values=["bc", "bn", "mz", "nw", "pt", "tc", "wb"],
    help="Genre to use for word-level roberta coreference model.")
flags.DEFINE_integer("wl_batch_size", default=16, help="Batch size to use for antecedent "
    "coreference scoring in word-level roberta coreference model.")
flags.DEFINE_enum("preprocess", default="none", enum_values=["addsays", "nocharacters", "none"],
    help="Type of script preprocessing.")
flags.DEFINE_enum("entity", default="all", enum_values=["person", "speaker", "all"],
    help="Filter entities criterion.")
flags.DEFINE_bool("merge_speakers", default=False, help="Merge clusters by speaker.")
flags.DEFINE_bool("provide_gold_mentions", default=False, help="Provide gold mentions to predictor.")
flags.DEFINE_bool("remove_gold_singletons", default=False, help="Remove singletons from annotations.")
flags.DEFINE_string("reference_scorer", default=p("coref/movie_coref/scorer/v8.01/scorer.pl"), 
    help="Path to conll reference scorer.")
flags.DEFINE_string("input_dir", default=p("data/movie_coref/results"),
    help="Directory containing the jsonlines")
flags.DEFINE_bool("run_train", default=False, help="Run baseline on training scripts.")
flags.DEFINE_string("output_dir", default=p("data/movie_coref/results/coreference/baselines"),
    help="Directory to which the baseline predictions will be saved")
flags.DEFINE_bool("overwrite", default=False, help="Overwrite predictions.")
flags.DEFINE_bool("append_results", default=False, help="Append results.")
flags.DEFINE_bool("use_gpu", default=False, help="Use cuda:0 gpu if available")
flags.DEFINE_integer("split_len", default=None, help="Number of words of the smaller screenplays."
    " If None, then no splitting occurs.")
flags.DEFINE_integer("overlap_len", default=0, help="Number of overlapping words between the"
    " smaller screenplays")

def main(argv):
    if len(argv) > 1:
        sys.exit("Extra command-line arguments.")
    if FLAGS.preprocess == "none":
        subdir = "regular"
    else:
        subdir = FLAGS.preprocess
    partition = "train" if FLAGS.run_train else "dev"
    input_file = os.path.join(FLAGS.input_dir, subdir, f"{partition}_wl.jsonlines")
    if FLAGS.split_len is not None:
        split_str = f"split_{FLAGS.split_len}.overlap_{FLAGS.overlap_len}."
    else:
        split_str = ""
    output_filename = (f"preprocess_{FLAGS.preprocess}.genre_{FLAGS.wl_genre}.{split_str}"
        f"{partition}_wl.jsonlines")
    output_file = os.path.join(FLAGS.output_dir, output_filename)
    result = baseline.wl_evaluate(FLAGS.reference_scorer, FLAGS.wl_config, FLAGS.wl_weights,
        FLAGS.wl_batch_size, FLAGS.wl_genre, input_file, output_file, FLAGS.entity, 
        FLAGS.merge_speakers, FLAGS.provide_gold_mentions, FLAGS.remove_gold_singletons, 
        FLAGS.split_len, FLAGS.overlap_len, FLAGS.overwrite, FLAGS.use_gpu)
    if FLAGS.append_results:
        with open(os.path.join(FLAGS.output_dir, f"{partition}.baseline.tsv"), "a") as fw:
            for metric, metric_result in result.items():
                for movie, movie_metric in metric_result.items():
                    fw.write("\t".join([FLAGS.preprocess, FLAGS.wl_genre, FLAGS.entity,
                        str(FLAGS.merge_speakers), str(FLAGS.provide_gold_mentions), 
                        str(FLAGS.remove_gold_singletons), str(FLAGS.split_len), 
                        str(FLAGS.overlap_len), metric, movie] + movie_metric.tolist()))
                    fw.write("\n")

if __name__ == '__main__':
    app.run(main)