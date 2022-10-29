"""Data structure for movie coreference for fine-tuning worl-level coreference
models
"""

import jsonlines
import math
import numpy as np
import string
from scorch.scores import muc, b_cubed, ceaf_e 
from torch.utils.data import DataLoader

pronouns = "you i he my him me his yourself mine your her she".split()
punctuation = list(string.punctuation)

class LabelSet:

    def __init__(self, labels: list[str], add_other: bool = True) -> None:
        """Initializer for label sets.

        Args:
            labels: list of class label names.
            add_other: If true, add a other class.
        """
        self._add_other = add_other
        self._labels = labels
        self._other_label = "<O>"
        assert self._other_label not in self._labels, (
            f"{self._other_label} cannot be a label")
        if add_other:
            self._labels.append(self._other_label)
        self._label_to_id: dict[str, int] = {}
        self._id_to_label: dict[int, str] = {}
        for i, label in enumerate(self._labels):
            self._label_to_id[label] = i
            self._id_to_label[i] = label
    
    def __len__(self) -> int:
        return len(self._labels)

    def __getitem__(self, key: int | str) -> int | str:
        """Get the label (label_id) from label_id (label)"""
        if isinstance(key, str):
            key = self.convert_label_to_key(key)
            return self._label_to_id[key]
        elif isinstance(key, int):
            return self._id_to_label[key]
        else:
            raise TypeError
    
    def convert_label_to_key(self, label: str) -> str:
        """Convert label to label key"""
        if label not in self._labels:
            if self._add_other:
                return self.other_label
            else:
                raise KeyError(f"label={label} not found in label set")
        else:
            return label
    
    @property
    def other_id(self) -> int:
        """Return label_id of other_label"""
        return self.__getitem__(self._other_label)
    
    @property
    def other_label(self) -> str:
        """Return other_label"""
        return self._other_label

    def __repr__(self) -> str:
        desc_list = []
        for i, l in self._id_to_label.items():
            desc_list.append(f"{i}:{l}")
        return " ".join(desc_list)

class PosLabelSet(LabelSet):
    def convert_label_to_key(self, label: str) -> str:
        if label.startswith("NN"):
            return "NOUN"
        elif label.startswith("VB"):
            return "VERB"
        elif label.startswith("JJ"):
            return "ADJECTIVE"
        elif label.startswith("RB"):
            return "ADVERB"
        else:
            return self.other_label

parse_labelset = LabelSet(list("SNCDE"))
pos_labelset = PosLabelSet(["NOUN", "VERB", "ADJECTIVE", "ADVERB"])
ner_labelset = LabelSet(["PERSON", "ORG", "GPE", "LOC"])

class Mention:
    """Mention objects represent mentions with head information. It contains
    three integers: start token index, end token index, and head token index
    of the mention. The end token index is inclusive. start <= head <= end.
    """
    def __init__(self, begin: int, end: int, head: int) -> None:
        self.begin = begin
        self.end = end
        self.head = head

    def __hash__(self) -> int:
        return hash((self.begin, self.end))

    def __lt__(self, other: "Mention") -> bool:
        return (self.begin, self.end) < (other.begin, other.end)

    def __repr__(self) -> str:
        return f"({self.begin},{self.end})"

class CorefDocument:
    """CorefDocument objects represent coreference-annotated and parsed movie
    script. It contains the following attributes: movie, rater, tokens, parse
    tags, part-of-speech tags, named entity tags, speaker tags, sentence
    offsets, and clusters. Clusters is a dictionary of character names to set
    of Mention objects.
    """
    def __init__(self, json: dict[str, any] = None) -> None:
        self.movie: str
        self.rater: str
        self.token: list[str]
        self.parse: list[str]
        self.parse_ids: list[int]
        self.pos: list[str]
        self.pos_ids: list[int]
        self.ner: list[str]
        self.ner_ids: list[int]
        self.is_pronoun: list[bool]
        self.is_punctuation: list[bool]
        self.speaker: list[str]
        self.sentence_offsets: list[list[int]]
        self.clusters: dict[str, set[Mention]]
        self.word_cluster_ids: list[int]
        self.word_head_ids: list[int]
        self.subword_ids: list[int]
        self.word_to_subword_offset: list[list[int]]
        self.subword_dataloader: DataLoader
        
        if json is not None:
            self.movie = json["movie"]
            self.rater = json["rater"]
            self.token = json["token"]
            self.parse = json["parse"]
            self.parse_ids = [parse_labelset[x] for x in self.parse]
            self.pos = json["pos"]
            self.pos_ids = [pos_labelset[x] for x in self.pos]
            self.ner = json["ner"]
            self.ner_ids = [ner_labelset[x] for x in self.ner]
            self.is_pronoun = [t.lower() in pronouns for t in self.token]
            self.is_punctuation = [t in punctuation for t in self.token]
            self.speaker = json["speaker"]
            self.sentence_offsets = json["sent_offset"]
            self.clusters = {}
            for character, mentions in json["clusters"].items():
                mentions = set([Mention(*x) for x in mentions])
                self.clusters[character] = mentions
            self.word_cluster_ids = np.zeros(len(self.token), dtype=int).tolist()
            self.word_head_ids = np.zeros(len(self.token), dtype=int).tolist()
            for i, (_, mentions) in enumerate(self.clusters.items()):
                for mention in mentions:
                    if len(mentions) > 1:
                        self.word_cluster_ids[mention.head] = i + 1
                    self.word_head_ids[mention.head] = 1
    
    def __repr__(self) -> str:
        desc = "Script\n=====\n\n"
        for i, j in self.sentence_offsets:
            sentence = self.token[i: j]
            desc += f"{sentence}\n"
        desc += "\n\nClusters\n========\n\n"
        for character, mentions in self.clusters.items():
            desc += f"{character}\n"
            sorted_mentions = sorted(mentions)
            mention_texts = []
            for mention in sorted_mentions:
                mention_text = " ".join(
                    self.token[mention.begin: mention.end + 1])
                mention_head = self.token[mention.head]
                mention_texts.append(f"{mention_text} ({mention_head})")
            n_rows = math.ceil(len(mention_texts)/3)
            for i in range(n_rows):
                row_mention_texts = mention_texts[i * 3: (i + 1) * 3]
                row_desc = "     ".join(
                    [f"{mention_text:25s}" for mention_text in row_mention_texts])
                desc += row_desc + "\n"
            desc += "\n"
        return desc

class CorefCorpus:
    """CorefCorpus is a list of CorefDocuments.
    """
    def __init__(self, file: str | None = None) -> None:
        self.documents: list[CorefDocument] = []
        if file is not None:
            with jsonlines.open(file) as reader:
                for json in reader:
                    self.documents.append(CorefDocument(json))
    
    def __len__(self) -> int:
        return len(self.documents)

    def __getitem__(self, i) -> CorefDocument:
        return self.documents[i]

class GraphNode:
    """Graph of character mention heads with edges connecting co-referring 
    head words.
    """
    def __init__(self, word_id: int):
        self.id = word_id
        self.neighbors: set[GraphNode] = set()
        self.visited = False

    def link(self, other: "GraphNode"):
        self.neighbors.add(other)
        other.neighbors.add(self)

    def __repr__(self) -> str:
        return str(self.id)

class Metric:
    """General metric class for precision, recall, and F1
    """
    def __init__(self, precision, recall, f1=None):
        self.precision = precision
        self.recall = recall
        if f1 is None:
            self.f1 = 2 * self.precision * self.recall / (
                1e-23 + self.precision + self.recall)
        else:
            self.f1 = f1
    
    def __repr__(self) -> str:
        return (f"precision={self.precision:.4f} recall={self.recall:.4f} "
                f"f1={self.f1:.4f}")

class CorefResult:
    """Data class to store gold and predicted coreference and character head
    labels.
    """

    def __init__(self) -> None:
        self._gold_word_clusters: list[set[tuple[int, int]]] = []
        self._gold_span_clusters: list[set[tuple[int, int, int]]] = []
        self._gold_characters: list[int] = []
        self._pred_word_clusters: list[set[tuple[int, int]]] = []
        self._pred_span_clusters: list[set[tuple[int, int, int]]] = []
        self._pred_characters: list[int] = []
        self._n_word = 0
        self._n_character = 0
        self._n_span = 0
        self._word_metric = None
        self._span_metric = None
        self._character_metric = None

    def add_word_clusters(
        self, gold_word_clusters: list[list[int]], 
        pred_word_clusters: list[list[int]]):
        i = self._n_word
        for cluster in gold_word_clusters:
            _cluster = set([(i, j) for j in cluster])
            self._gold_word_clusters.append(_cluster)
        for cluster in pred_word_clusters:
            _cluster = set([(i, j) for j in cluster])
            self._pred_word_clusters.append(_cluster)
        self._n_word += 1
    
    def add_span_clusters(
        self, gold_span_clusters: list[list[list[int]]], 
        pred_span_clusters: list[list[list[int]]]):
        i = self._n_span
        for cluster in gold_span_clusters:
            _cluster = set([(i, j, k) for j, k in cluster])
            self._gold_span_clusters.append(_cluster)
        for cluster in pred_span_clusters:
            _cluster = set([(i, j, k) for j, k in cluster])
            self._pred_span_clusters.append(_cluster)
        self._n_span += 1

    def add_characters(
        self, gold_characters: list[int], pred_characters: list[int]):
        assert len(gold_characters) == len(pred_characters)
        self._gold_characters.extend(gold_characters)
        self._pred_characters.extend(pred_characters)
        self._n_character += 1

    def score(self):
        if self._n_word > 0:
            muc_metric = Metric(*muc(
                self._gold_word_clusters, self._pred_word_clusters))
            b_cubed_metric = Metric(*b_cubed(
                self._gold_word_clusters, self._pred_word_clusters))
            ceaf_e_metric = Metric(*ceaf_e(
                self._gold_word_clusters, self._pred_word_clusters))
            self._word_metric = (muc_metric, b_cubed_metric, ceaf_e_metric)
        if self._n_span > 0:
            muc_metric = Metric(*muc(
                self._gold_span_clusters, self._pred_span_clusters))
            b_cubed_metric = Metric(*b_cubed(
                self._gold_span_clusters, self._pred_span_clusters))
            ceaf_e_metric = Metric(*ceaf_e(
                self._gold_span_clusters, self._pred_span_clusters))
            self._span_metric = (muc_metric, b_cubed_metric, ceaf_e_metric)
        if self._n_character > 0:
            _gold = np.array(self._gold_characters)
            _pred = np.array(self._pred_characters)
            tp = ((_gold == 1) & (_pred == 1)).sum()
            fp = ((_gold == 0) & (_pred == 1)).sum()
            fn = ((_gold == 1) & (_pred == 0)).sum()
            precision = tp/(tp + fp + 1e-23)
            recall = tp/(tp + fn + 1e-23)
            self._character_metric = Metric(precision, recall)
    
    def __repr__(self) -> str:
        desc = ""
        if self._word_metric:
            muc_metric, b_cubed_metric, ceaf_e_metric = self._word_metric
            desc += (f"Word-Level Coref:= MUC: {muc_metric}, B_cubed: "
                    f"{b_cubed_metric}, CEAF-e: {ceaf_e_metric}\n")
        if self._span_metric:
            muc_metric, b_cubed_metric, ceaf_e_metric = self._span_metric
            desc += (f"Span-Level Coref:= MUC: {muc_metric}, B_cubed: "
                    f"{b_cubed_metric}, CEAF-e: {ceaf_e_metric}\n")
        if self._character_metric:
            desc += f"Character-Head: {self._character_metric}\n"
        return desc