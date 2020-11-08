import os
import numpy as np
from typing import List, Generator
from PIL import Image

from calamari_ocr.ocr.backends.dataset.data_types import InputSample, SampleMeta
from calamari_ocr.ocr.backends.dataset.datareader import DataReader
from calamari_ocr.ocr.backends.dataset.datareader.abbyy.xml.reader import XMLReader
from calamari_ocr.ocr.backends.dataset.datareader.abbyy.xml.writer import XMLWriter
from tqdm import tqdm

from calamari_ocr.ocr.datasets import DataSetMode
from calamari_ocr.utils import split_all_ext


class AbbyyReader(DataReader):
    def __init__(self,
                 mode: DataSetMode,
                 files: List[str] = None,
                 xmlfiles: List[str] = None,
                 skip_invalid=False,
                 remove_invalid=True,
                 binary=False,
                 non_existing_as_empty=False,
                 ):

        """ Create a dataset from a Path as String

        Parameters
         ----------
        files : [], required
            image files
        skip_invalid : bool, optional
            skip invalid files
        remove_invalid : bool, optional
            remove invalid files
        """

        super().__init__(
            mode,
            skip_invalid, remove_invalid)

        self.xmlfiles = xmlfiles if xmlfiles else []
        self.files = files if files else []

        self._non_existing_as_empty = non_existing_as_empty
        if len(self.xmlfiles) == 0:
            from calamari_ocr.ocr.datasets import DataSetType
            self.xmlfiles = [split_all_ext(p)[0] + DataSetType.gt_extension(DataSetType.ABBYY) for p in files]

        if len(self.files) == 0:
            self.files = [None] * len(self.xmlfiles)

        self.book = XMLReader(self.files, self.xmlfiles, skip_invalid, remove_invalid).read()
        self.binary = binary

        for p, page in enumerate(self.book.pages):
            for l, line in enumerate(page.getLines()):
                for f, fo in enumerate(line.formats):
                    self.add_sample({
                        "image_path": page.imgFile,
                        "xml_path": page.xmlFile,
                        "id": "{}_{}_{}_{}".format(os.path.splitext(page.xmlFile if page.xmlFile else page.imgFile)[0], p, l, f),
                        "line": line,
                        "format": fo,
                    })

    def store_text(self, sentence, sample, output_dir, extension):
        # an Abbyy dataset stores the prediction in one XML file
        sample["format"].text = sentence

    def store(self, extension):
        for page in tqdm(self.book.pages, desc="Writing Abbyy files", total=len(self.book.pages)):
            XMLWriter.write(page, split_all_ext(page.xmlFile)[0] + extension)

    def _sample_iterator(self):
        return zip(self.files, self.xmlfiles)

    def _load_sample(self, sample, text_only) -> Generator[InputSample, None, None]:
        image_path, xml_path = sample

        book = XMLReader([image_path], [xml_path], self.skip_invalid, self.remove_invalid).read()

        if self.mode == DataSetMode.TRAIN or self.mode == DataSetMode.PREDICT or self.mode == DataSetMode.PRED_AND_EVAL:
            img = np.array(Image.open(image_path))
            if self.binary:
                img = img > 0.9
        else:
            img = None

        for p, page in enumerate(book.pages):
            for l, line in enumerate(page.getLines()):
                for f, fo in enumerate(line.formats):
                    sample_id = "{}_{}_{}_{}".format(os.path.splitext(page.xmlFile if page.xmlFile else page.imgFile)[0], p, l, f)
                    text = None
                    if self.mode == DataSetMode.EVAL or self.mode == DataSetMode.TRAIN or self.mode == DataSetMode.PRED_AND_EVAL:
                        text = fo.text

                    if text_only:
                        yield InputSample(None, text, SampleMeta(id=sample_id))

                    else:
                        cut_img = None
                        if self.mode == DataSetMode.TRAIN or self.mode == DataSetMode.PREDICT or self.mode == DataSetMode.PRED_AND_EVAL:
                            ly, lx = img.shape

                            # Cut the Image
                            cut_img = img[line.rect.top: -ly + line.rect.bottom, line.rect.left: -lx + line.rect.right]

                            # add padding as required from normal files
                            cut_img = np.pad(cut_img, ((3, 3), (0, 0)), mode='constant', constant_values=cut_img.max())

                        yield InputSample(cut_img, text, SampleMeta(id=sample_id))
