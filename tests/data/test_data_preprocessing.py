# Copyright The FMS HF Tuning Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Standard
import glob
import json
import os
import tempfile

# Third Party
from datasets import Dataset, DatasetDict, IterableDataset
from PIL import Image
from transformers import AutoProcessor, AutoTokenizer, DataCollatorForSeq2Seq
from trl import DataCollatorForCompletionOnlyLM
import datasets
import numpy as np
import pyarrow
import pytest
import yaml

# First Party
from tests.artifacts.language_models import MAYKEYE_TINY_LLAMA_CACHED
from tests.artifacts.predefined_data_configs import (
    DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
    DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_AND_SPLIT_YAML,
    DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_AND_SPLIT_YAML_2,
    DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_YAML,
    DATA_CONFIG_MULTITURN_DATA_YAML,
    DATA_CONFIG_PRETOKENIZE_DATA_YAML,
    DATA_CONFIG_RENAME_SELECT_COLUMNS,
    DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
    DATA_CONFIG_YAML_STREAMING_INPUT_OUTPUT,
    DATA_CONFIG_YAML_STREAMING_PRETOKENIZED,
)
from tests.artifacts.testdata import (
    CHAT_DATA_MULTI_TURN,
    CHAT_DATA_SINGLE_TURN,
    IMAGE_DATASET,
    TWITTER_COMPLAINTS_DATA_ARROW,
    TWITTER_COMPLAINTS_DATA_DIR_JSON,
    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
    TWITTER_COMPLAINTS_DATA_JSON,
    TWITTER_COMPLAINTS_DATA_JSONL,
    TWITTER_COMPLAINTS_DATA_PARQUET,
    TWITTER_COMPLAINTS_TOKENIZED_ARROW,
    TWITTER_COMPLAINTS_TOKENIZED_JSON,
    TWITTER_COMPLAINTS_TOKENIZED_JSONL,
    TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
)
from tests.artifacts.vision_models import (
    TINY_GRANITE_VISION_MODEL_NAME,
    TINY_LLAMA_VISION_MODEL_NAME,
)

# Local
from tuning.config import configs
from tuning.config.acceleration_configs import AttentionAndDistributedPackingConfig
from tuning.data.collators import VisionDataCollator
from tuning.data.data_config import (
    DataHandlerConfig,
    DataPreProcessorConfig,
    DataSetConfig,
)
from tuning.data.data_preprocessing_utils import get_data_collator
from tuning.data.data_processors import DataPreProcessor, get_datapreprocessor
from tuning.data.setup_dataprocessor import (
    is_pretokenized_dataset,
    process_dataargs,
    process_dataconfig_file,
)
from tuning.data.utils import try_concatenate_datasets

MODEL_NAME = MAYKEYE_TINY_LLAMA_CACHED


@pytest.mark.parametrize(
    "datafile, column_names",
    [
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            set(["ID", "Label", "input", "output"]),
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
            set(["ID", "Label", "input", "output", "sequence"]),
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            set(["ID", "Label", "input", "output"]),
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_JSONL,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "attention_mask",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                ]
            ),
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_ARROW,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "attention_mask",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                ]
            ),
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "attention_mask",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                ]
            ),
        ),
        (
            TWITTER_COMPLAINTS_DATA_JSONL,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
        ),
        (
            TWITTER_COMPLAINTS_DATA_ARROW,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
        ),
        (
            TWITTER_COMPLAINTS_DATA_PARQUET,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
        ),
    ],
)
def test_load_dataset_with_datafile(datafile, column_names):
    """Ensure that both dataset is loaded with datafile."""
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    load_dataset = processor.load_dataset(
        datasetconfig=None,
        streaming=processor.processor_config.streaming,
        splitName="train",
        datafile=datafile,
    )
    assert set(load_dataset.column_names) == column_names


@pytest.mark.parametrize("hf_dataset, splitName", [("squad", "validation")])
def test_load_dataset_with_hf_dataset(hf_dataset, splitName):
    """Ensure that hf dataset could be loaded."""
    datasetconfig = DataSetConfig(
        name="text_dataset_input_output_masking", data_paths=[hf_dataset]
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    load_dataset = processor.load_dataset(
        datasetconfig=datasetconfig,
        streaming=processor.processor_config.streaming,
        splitName=splitName,
        datafile=None,
    )
    assert processor.processor_config.streaming is False
    assert isinstance(load_dataset, Dataset)


@pytest.mark.parametrize(
    "datafile, column_names, datasetconfigname, builder",
    [
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            set(["ID", "Label", "input", "output"]),
            "text_dataset_input_output_masking",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
            set(["ID", "Label", "input", "output", "sequence"]),
            "text_dataset_input_output_masking",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            set(["ID", "Label", "input", "output"]),
            "text_dataset_input_output_masking",
            None,
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_JSONL,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "attention_mask",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                ]
            ),
            "pretokenized_dataset",
            None,
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "attention_mask",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                ]
            ),
            "pretokenized_dataset",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_JSONL,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
            "apply_custom_data_template",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_ARROW,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
            "apply_custom_data_template",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_PARQUET,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
            "apply_custom_data_template",
            None,
        ),
        (
            TWITTER_COMPLAINTS_DATA_PARQUET,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
            "apply_custom_data_template",
            "parquet",
        ),
    ],
)
def test_load_dataset_with_datasetconfig(
    datafile, column_names, datasetconfigname, builder
):
    """Ensure that both dataset is loaded with datafile."""
    datasetconfig = DataSetConfig(
        name=datasetconfigname, data_paths=[datafile], builder=builder
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    load_dataset = processor.load_dataset(
        datasetconfig=datasetconfig,
        streaming=processor.processor_config.streaming,
        splitName="train",
        datafile=None,
    )
    assert set(load_dataset.column_names) == column_names


@pytest.mark.parametrize(
    "data_paths, datasetconfigname",
    [
        (
            ["fake/path"],
            "apply_custom_data_template",
        ),
        (
            [
                TWITTER_COMPLAINTS_DATA_PARQUET.replace(
                    "twitter_complaints_small.parquet", "not_exist.parquet"
                )
            ],
            "apply_custom_data_template",
        ),
    ],
)
def test_load_dataset_with_non_exist_path(data_paths, datasetconfigname):
    """Ensure that load_dataset raises error for non-exist paths."""
    datasetconfig = DataSetConfig(name=datasetconfigname, data_paths=data_paths)
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    with pytest.raises((datasets.exceptions.DatasetNotFoundError, ValueError)):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


@pytest.mark.parametrize(
    "datafile, datasetconfigname, builder",
    [
        (TWITTER_COMPLAINTS_DATA_PARQUET, "apply_custom_data_template", "arrow"),
    ],
)
def test_load_dataset_with_datasetconfig_incorrect_builder(
    datafile, datasetconfigname, builder
):
    """Ensure that directory with incorrect builder cannot be passed in datasetconfig."""
    datasetconfig = DataSetConfig(
        name=datasetconfigname, data_paths=[datafile], builder=builder
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    # pylint: disable=c-extension-no-member
    with pytest.raises(pyarrow.lib.ArrowInvalid):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


@pytest.mark.parametrize(
    "datafile, datasetconfigname",
    [
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            "text_dataset_input_output_masking",
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            "text_dataset_input_output_masking",
        ),
        (TWITTER_COMPLAINTS_TOKENIZED_JSONL, "pretokenized_dataset"),
        (TWITTER_COMPLAINTS_TOKENIZED_PARQUET, "pretokenized_dataset"),
        (TWITTER_COMPLAINTS_DATA_JSONL, "apply_custom_data_template"),
        (TWITTER_COMPLAINTS_DATA_PARQUET, "apply_custom_data_template"),
    ],
)
def test_load_dataset_with_dataconfig_and_datafile(datafile, datasetconfigname):
    """Ensure that both datasetconfig and datafile cannot be passed."""
    datasetconfig = DataSetConfig(name=datasetconfigname, data_paths=[datafile])
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    with pytest.raises(ValueError):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=datafile,
        )


@pytest.mark.parametrize(
    "datasetconfig, column_names",
    [
        (
            DataSetConfig(
                name="text_dataset_input_output_masking",
                data_paths=[TWITTER_COMPLAINTS_DATA_DIR_JSON],
            ),
            set(["ID", "Label", "input", "output"]),
        ),
        (
            DataSetConfig(
                name="text_dataset_input_output_masking",
                data_paths=[TWITTER_COMPLAINTS_DATA_DIR_JSON],
                builder="json",
            ),
            set(["ID", "Label", "input", "output"]),
        ),
    ],
)
def test_load_dataset_with_dataconfig_and_datafolder(datasetconfig, column_names):
    """Ensure that directory can be passed in datasetconfig with/without builder."""
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    load_dataset = processor.load_dataset(
        datasetconfig=datasetconfig,
        streaming=processor.processor_config.streaming,
        splitName="train",
        datafile=None,
    )
    assert set(load_dataset.column_names) == column_names


@pytest.mark.parametrize(
    "datasetconfig",
    [
        DataSetConfig(
            name="text_dataset_input_output_masking",
            data_paths=[TWITTER_COMPLAINTS_DATA_DIR_JSON],
            builder="arrow",
        ),
    ],
)
def test_load_dataset_with_dataconfig_and_datafolder_incorrect_builder(datasetconfig):
    """Ensure that directory with incorrect builder cannot be passed in datasetconfig."""
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    # pylint: disable=c-extension-no-member
    with pytest.raises(pyarrow.lib.ArrowInvalid):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


def test_load_dataset_without_dataconfig_and_datafile():
    """Ensure that both datasetconfig and datafile cannot be None."""
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    with pytest.raises(ValueError):
        processor.load_dataset(
            datasetconfig=None,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


@pytest.mark.parametrize(
    "data_paths, column_names, datasetconfigname, builder",
    [
        (
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                TWITTER_COMPLAINTS_DATA_DIR_JSON,
            ],
            set(["ID", "Label", "input", "output"]),
            "text_dataset_input_output_masking",
            None,
        ),
        (
            [
                TWITTER_COMPLAINTS_DATA_DIR_JSON,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            ],
            set(["ID", "Label", "input", "output"]),
            "text_dataset_input_output_masking",
            None,
        ),
    ],
)
def test_load_dataset_with_datasetconfig_files_folders(
    data_paths, column_names, datasetconfigname, builder
):
    """Ensure that load_dataset works with passing combination of files and folders."""
    datasetconfig = DataSetConfig(
        name=datasetconfigname, data_paths=data_paths, builder=builder
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    load_dataset = processor.load_dataset(
        datasetconfig=datasetconfig,
        streaming=processor.processor_config.streaming,
        splitName="train",
        datafile=None,
    )
    assert set(load_dataset.column_names) == column_names


@pytest.mark.parametrize(
    "data_paths, datasetconfigname, builder",
    [
        (
            [
                TWITTER_COMPLAINTS_DATA_DIR_JSON,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            ],
            "text_dataset_input_output_masking",
            "arrow",
        ),
    ],
)
def test_load_dataset_with_datasetconfig_files_folders_incorrect_builder(
    data_paths, datasetconfigname, builder
):
    """
    Ensure that load_dataset with passing combination of
    files and folders does support mismatch in format
    """
    datasetconfig = DataSetConfig(
        name=datasetconfigname, data_paths=data_paths, builder=builder
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    with pytest.raises(ValueError):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


@pytest.mark.parametrize(
    "data, result",
    [
        (TWITTER_COMPLAINTS_DATA_JSONL, False),
        (
            Dataset.from_list(
                [
                    {
                        "input_ids": [9437, 29, 210],
                        "attention_mask": [1, 1, 1],
                        "labels": [1, 20, 30],
                    }
                ]
            ),
            True,
        ),
    ],
)
def test_is_pretokenized_data(data, result):
    """Ensure that the correct collator type is fetched based on the data args"""
    assert is_pretokenized_dataset(data=data) == result


@pytest.mark.parametrize(
    "packing, response_template, formatted_train_dataset,\
     max_seq_length, instruction_template, is_padding_free, expected_collator",
    [
        (
            False,
            "\n### Label:",
            datasets.load_dataset(
                "json",
                data_files=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                split="train",
            ),
            1024,
            None,
            False,
            DataCollatorForCompletionOnlyLM,
        ),
        (
            False,
            "\n### Label:",
            datasets.load_dataset(
                "json",
                data_files=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                split="train",
            ),
            1024,
            "\n### Text:",
            False,
            DataCollatorForCompletionOnlyLM,
        ),
        (
            False,
            None,
            datasets.load_dataset(
                "json",
                data_files=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                split="train",
            ),
            1024,
            None,
            True,
            DataCollatorForSeq2Seq,
        ),
    ],
)
def test_get_data_collator(
    packing,
    response_template,
    formatted_train_dataset,
    max_seq_length,
    instruction_template,
    is_padding_free,
    expected_collator,
):
    """Ensure that the correct collator type is fetched based on the data args"""
    collator = get_data_collator(
        packing,
        response_template,
        AutoTokenizer.from_pretrained(MODEL_NAME),
        is_pretokenized_dataset(formatted_train_dataset),
        max_seq_length,
        instruction_template,
        is_padding_free,
    )
    assert isinstance(collator, expected_collator)


# Tests for validating data args
# Invalid args return ValueError
@pytest.mark.parametrize(
    "data_args, packing",
    [
        # dataset_text_field with no response_template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
                dataset_text_field="output",
            ),
            False,
        ),
        # Data formatter with no response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
                data_formatter_template="### Input: {{input}} \n\n### Response: {{output}}",
            ),
            False,
        ),
        # Response template with no dataset_text_field or formatter
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
                response_template="\n### Label:",
            ),
            False,
        ),
        # JSONL without input / output for no single sequence arguments
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
            ),
            False,
        ),
        # Pretokenized dataset with dataset_text_field
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                dataset_text_field="output",
            ),
            False,
        ),
        # Pretokenized dataset with data formatter
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                data_formatter_template="### Input: {{input}} \n\n### Response: {{output}}",
            ),
            False,
        ),
        # Pretokenized dataset with response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                response_template="\n### Label:",
            ),
            False,
        ),
        # Pretokenized training dataset with validation data not pretokenized
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                validation_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
            ),
            False,
        ),
        # Pretokenized data with dataset_text_field and response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                response_template="\n### Label:",
                dataset_text_field="output",
            ),
            False,
        ),
    ],
)
def test_process_data_args_throws_error_where_needed(data_args, packing):
    """Ensure that respective errors are thrown for incorrect data arguments"""
    with pytest.raises(ValueError):
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        TRAIN_ARGS = configs.TrainingArguments(
            packing=packing,
            max_seq_length=1024,
            output_dir="tmp",  # Not needed but positional
        )
        (_, _, _, _, _, _) = process_dataargs(data_args, tokenizer, TRAIN_ARGS)


@pytest.mark.parametrize(
    "data_config_path, data_path",
    [
        (
            DATA_CONFIG_YAML_STREAMING_INPUT_OUTPUT,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
        ),
        (DATA_CONFIG_YAML_STREAMING_PRETOKENIZED, TWITTER_COMPLAINTS_TOKENIZED_JSON),
    ],
)
def test_process_dataconfig_file_with_streaming(data_config_path, data_path):
    """
    Ensure that datasets are formatted and validated correctly
    based on the arguments passed in config file.
    """
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"][0] = data_path
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_column_name and output_column_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "input_column_name": "input",
            "output_column_name": "output",
        }

    # Modify formatted_text_column_name and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name == "apply_custom_data_template":
        template = (
            '### Input: {{element["Tweet text"]}} \n\n ### Response: {{text_label}}'
            + "{{eos_token}}"
        )
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "formatted_text_column_name": formatted_dataset_field,
            "template": template,
        }

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        max_steps=1,
        output_dir="tmp",  # Not needed but positional
    )

    (train_set, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)
    assert isinstance(train_set, IterableDataset)
    if datasets_name == "text_dataset_input_output_masking":
        column_names = set(["input_ids", "attention_mask", "labels"])
        assert set(train_set.column_names) == column_names
    elif datasets_name == "pretokenized_dataset":
        assert set(["input_ids", "labels"]).issubset(set(train_set.column_names))
    elif datasets_name == "apply_custom_data_template":
        assert formatted_dataset_field in set(train_set.column_names)
    with pytest.raises(ValueError):
        _ = process_dataconfig_file(
            data_args, TRAIN_ARGS, tokenizer, is_padding_free=True
        )


def test_concatenate_dict_with_multi_keys():
    """
    Ensure that concatenated datasets are formatted and validated correctly.
    Ensures the returned dataset has proper concatenation

    Details for Concatenation Operation of dictionary with different keys
        data                        => { "train": Values }
        data_dict1                  => { "train": Values, "train2": Values }
        data_dict2                  => { "train": Values, "train2": Values, "train3": Values }
        ------------------------------------------------------------------------------------------
        concatenated_dataset        => { "train": Values*3, "train2": Values*2, "train3": Values }
    """

    data_paths = TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON
    data = datasets.load_dataset("json", data_files=[data_paths])
    data_streaming = datasets.load_dataset(
        "json", data_files=[data_paths], streaming=True
    )

    data_dict1 = DatasetDict()
    data_dict1["train"] = data["train"]
    data_dict1["train2"] = data["train"]

    data_dict2 = DatasetDict()
    data_dict2["train"] = data["train"]
    data_dict2["train2"] = data["train"]
    data_dict2["train3"] = data["train"]

    concatenated_dataset = try_concatenate_datasets([data, data_dict1, data_dict2])

    # Check if the datasets are concatenated correctly
    assert (
        len(concatenated_dataset) == 3
        and concatenated_dataset["train"].num_rows == data["train"].num_rows * 3
        and concatenated_dataset["train2"].num_rows == data["train"].num_rows * 2
        and concatenated_dataset["train3"].num_rows == data["train"].num_rows
    )
    # Assert ValueError on concatenation of mixed dataset types (only same types supported)
    with pytest.raises(ValueError):
        try_concatenate_datasets([data, data_streaming])


@pytest.mark.parametrize(
    "data_config_path, data_path",
    [
        (
            DATA_CONFIG_YAML_STREAMING_INPUT_OUTPUT,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
        ),
    ],
)
def test_process_dataconfig_file_with_streaming_no_max_steps_errors(
    data_config_path, data_path
):
    """Ensure that if max steps aren't passed with streaming, error is raised"""
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"][0] = data_path
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_column_name and output_column_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "input_column_name": "input",
            "output_column_name": "output",
        }

    # Modify formatted_text_column_name and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name == "apply_custom_data_template":
        template = (
            '### Input: {{element["Tweet text"]}} \n\n ### Response: {{text_label}}'
            + "{{eos_token}}"
        )
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "formatted_text_column_name": formatted_dataset_field,
            "template": template,
        }

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
    )

    with pytest.raises(ValueError):
        (_, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)


@pytest.mark.parametrize(
    "data_config_path, data_path",
    [
        (
            DATA_CONFIG_YAML_STREAMING_INPUT_OUTPUT,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
        ),
    ],
)
def test_process_dataconfig_file_with_streaming_and_multipack_throws_error(
    data_config_path, data_path
):
    """Ensure that if multipack is passed with streaming, error is raised"""
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"][0] = data_path
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_field_name and output_field_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "input_field_name": "input",
            "output_field_name": "output",
        }

    # Modify dataset_text_field and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name == "apply_custom_data_template":
        template = (
            '### Input: {{element["Tweet text"]}} \n\n ### Response: {{text_label}}'
            + "{{eos_token}}"
        )
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "dataset_text_field": formatted_dataset_field,
            "template": template,
        }

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
        max_steps=1,
    )

    attention_and_distributed_packing_config = AttentionAndDistributedPackingConfig(
        None, None
    )
    attention_and_distributed_packing_config.multipack = 16

    is_multipack = attention_and_distributed_packing_config.is_multipack

    with pytest.raises(ValueError):
        (_, _, _) = process_dataconfig_file(
            data_args, TRAIN_ARGS, tokenizer, is_multipack=is_multipack
        )


@pytest.mark.parametrize(
    "data_config_path, data_path",
    [
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_JSON),
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_JSONL),
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_PARQUET),
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_ARROW),
        (DATA_CONFIG_PRETOKENIZE_DATA_YAML, TWITTER_COMPLAINTS_TOKENIZED_JSON),
        (DATA_CONFIG_PRETOKENIZE_DATA_YAML, TWITTER_COMPLAINTS_TOKENIZED_JSONL),
        (DATA_CONFIG_PRETOKENIZE_DATA_YAML, TWITTER_COMPLAINTS_TOKENIZED_PARQUET),
        (DATA_CONFIG_PRETOKENIZE_DATA_YAML, TWITTER_COMPLAINTS_TOKENIZED_ARROW),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
        ),
    ],
)
def test_process_dataconfig_file(data_config_path, data_path):
    """
    Ensure that datasets are formatted and validated correctly
    based on the arguments passed in config file.
    """
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"][0] = data_path
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_column_name and output_column_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "input_column_name": "input",
            "output_column_name": "output",
        }

    # Modify formatted_text_column_name and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name in (
        "apply_custom_data_template",
        "apply_custom_data_jinja_template",
    ):
        template = (
            '### Input: {{element["Tweet text"]}} \n\n ### Response: {{text_label}}'
            + "{{eos_token}}"
        )
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "formatted_text_column_name": formatted_dataset_field,
            "template": template,
        }

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
    )

    (train_set, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)
    assert isinstance(train_set, Dataset)
    if datasets_name == "text_dataset_input_output_masking":
        column_names = set(["input_ids", "attention_mask", "labels"])
        assert set(train_set.column_names) == column_names
    elif datasets_name == "pretokenized_dataset":
        assert set(["input_ids", "labels"]).issubset(set(train_set.column_names))
    elif datasets_name in (
        "apply_custom_data_template",
        "apply_custom_data_jinja_template",
    ):
        assert formatted_dataset_field in set(train_set.column_names)


@pytest.mark.parametrize(
    "data_config_path, data_path, add_eos_token",
    [
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_JSON, True),
        (DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML, TWITTER_COMPLAINTS_DATA_JSON, False),
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            TWITTER_COMPLAINTS_DATA_JSON,
            True,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            True,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            False,
        ),
    ],
)
def test_process_datahandler_eos_token(data_config_path, data_path, add_eos_token):
    """
    Ensure that the data handlers correctly apply
    eos_token.
    """
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"][0] = data_path
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_column_name and output_column_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"][
            "input_column_name"
        ] = "input"
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"][
            "output_column_name"
        ] = "output"
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"][
            "add_eos_token"
        ] = add_eos_token

    # Modify formatted_text_column_name and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name in (
        "apply_custom_data_template",
        "apply_custom_data_jinja_template",
    ):
        template = (
            "### Input: {{element['Tweet text']}} \n\n ### Response: {{text_label}}"
        )
        if add_eos_token:
            template += "{{eos_token}}"
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"][
            "formatted_text_column_name"
        ] = formatted_dataset_field
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"][
            "template"
        ] = template

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.add_special_tokens({"eos_token": "</s>"})

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
    )

    (train_set, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)
    assert isinstance(train_set, Dataset)
    if datasets_name == "text_dataset_input_output_masking":
        column_names = set(["input_ids", "attention_mask", "labels"])
        assert set(train_set.column_names) == column_names
        assert (
            train_set[0]["input_ids"][-1] == tokenizer.eos_token_id
            if add_eos_token
            else train_set[0]["input_ids"][-1] != tokenizer.eos_token_id
        )
    elif datasets_name == "pretokenized_dataset":
        assert set(["input_ids", "labels"]).issubset(set(train_set.column_names))
    elif datasets_name in (
        "apply_custom_data_template",
        "apply_custom_data_jinja_template",
    ):
        assert formatted_dataset_field in set(train_set.column_names)
        assert (
            train_set[0][formatted_dataset_field].endswith(tokenizer.eos_token)
            if add_eos_token
            else not train_set[0][formatted_dataset_field].endswith(tokenizer.eos_token)
        )


@pytest.mark.parametrize(
    "data_config_path, data_path_list",
    [
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            [TWITTER_COMPLAINTS_DATA_JSON, TWITTER_COMPLAINTS_DATA_JSON],
        ),
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            [
                TWITTER_COMPLAINTS_DATA_JSONL,
                TWITTER_COMPLAINTS_DATA_JSONL,
                TWITTER_COMPLAINTS_DATA_JSONL,
            ],
        ),
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            [TWITTER_COMPLAINTS_DATA_PARQUET, TWITTER_COMPLAINTS_DATA_PARQUET],
        ),
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            [TWITTER_COMPLAINTS_DATA_ARROW, TWITTER_COMPLAINTS_DATA_ARROW],
        ),
        (
            DATA_CONFIG_APPLY_CUSTOM_TEMPLATE_YAML,
            [TWITTER_COMPLAINTS_DATA_JSON, TWITTER_COMPLAINTS_DATA_PARQUET],
        ),
        (
            DATA_CONFIG_PRETOKENIZE_DATA_YAML,
            [TWITTER_COMPLAINTS_TOKENIZED_JSON, TWITTER_COMPLAINTS_TOKENIZED_JSON],
        ),
        (
            DATA_CONFIG_PRETOKENIZE_DATA_YAML,
            [TWITTER_COMPLAINTS_TOKENIZED_JSONL, TWITTER_COMPLAINTS_TOKENIZED_JSONL],
        ),
        (
            DATA_CONFIG_PRETOKENIZE_DATA_YAML,
            [
                TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
                TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
                TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
            ],
        ),
        (
            DATA_CONFIG_PRETOKENIZE_DATA_YAML,
            [TWITTER_COMPLAINTS_TOKENIZED_ARROW, TWITTER_COMPLAINTS_TOKENIZED_ARROW],
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            ],
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            ],
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            ],
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
            ],
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            ],
        ),
    ],
)
def test_process_dataconfig_multiple_files(data_config_path, data_path_list):
    """
    Ensure that datasets with multiple files are formatted and
    validated correctly based on the arguments passed in config file.
    """
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"] = data_path_list
    datasets_name = yaml_content["datasets"][0]["name"]

    # Modify input_column_name and output_column_name according to dataset
    if datasets_name == "text_dataset_input_output_masking":
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "input_column_name": "input",
            "output_column_name": "output",
        }

    # Modify formatted_text_column_name and template according to dataset
    formatted_dataset_field = "formatted_data_field"
    if datasets_name == "apply_custom_data_template":
        template = (
            '### Input: {{element["Tweet text"]}} \n\n ### Response: {{text_label}}'
            + "{{eos_token}}"
        )
        yaml_content["datasets"][0]["data_handlers"][0]["arguments"]["fn_kwargs"] = {
            "formatted_text_column_name": formatted_dataset_field,
            "template": template,
        }

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
    )

    (train_set, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)
    assert isinstance(train_set, Dataset)
    if datasets_name == "text_dataset_input_output_masking":
        column_names = set(["input_ids", "attention_mask", "labels"])
        assert set(train_set.column_names) == column_names
    elif datasets_name == "pretokenized_dataset":
        assert set(["input_ids", "labels"]).issubset(set(train_set.column_names))
    elif datasets_name == "apply_custom_data_template":
        assert formatted_dataset_field in set(train_set.column_names)


@pytest.mark.parametrize(
    "data_config_path, data_paths, builder",
    [
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*.json")],
            None,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*.json")],
            "json",
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*")],
            "json",
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*complaints*")],
            "json",
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [TWITTER_COMPLAINTS_DATA_DIR_JSON],
            None,
        ),
        (
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            [TWITTER_COMPLAINTS_DATA_DIR_JSON],
            "json",
        ),
    ],
)
def test_process_dataconfig_multiple_files_folders_with_globbing(
    data_config_path, data_paths, builder
):
    """
    Ensure that datasets files matching globbing pattern are formatted and
    validated correctly based on the arguments passed in config file.
    """
    with open(data_config_path, "r") as f:
        yaml_content = yaml.safe_load(f)

    yaml_content["datasets"][0]["data_paths"] = data_paths
    yaml_content["datasets"][0]["builder"] = builder

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        output_dir="tmp",  # Not needed but positional
    )

    (train_set, _, _) = process_dataconfig_file(data_args, TRAIN_ARGS, tokenizer)
    assert isinstance(train_set, Dataset)
    assert set(["input_ids", "attention_mask", "labels"]).issubset(
        set(train_set.column_names)
    )

    path_or_pattern = data_paths[0]
    if os.path.isdir(path_or_pattern):
        # Construct a pattern for JSON files in this directory
        pattern = os.path.join(path_or_pattern, "*.json")
    else:
        # Assume path_or_pattern is already a pattern
        pattern = path_or_pattern

    data_len = 0
    for file in glob.glob(pattern):
        with open(file, "r") as f:
            data_len += len(json.load(f))

    assert len(train_set) == data_len


@pytest.mark.parametrize(
    "data_paths, datasetconfigname, builder",
    [
        (
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*")],
            "tokenize_and_apply_input_masking",
            None,
        ),
        (
            [os.path.join(TWITTER_COMPLAINTS_DATA_DIR_JSON, "*complaints*")],
            "tokenize_and_apply_input_masking",
            None,
        ),
        (["*squad"], "tokenize_and_apply_input_masking", None),
        (
            [TWITTER_COMPLAINTS_DATA_DIR_JSON.replace("datafolder", "dataf*")],
            "tokenize_and_apply_input_masking",
            None,
        ),
        (
            [TWITTER_COMPLAINTS_DATA_DIR_JSON],
            DATA_CONFIG_TOKENIZE_AND_APPLY_INPUT_MASKING_YAML,
            "parquet",
        ),
    ],
)
def test_process_dataconfig_multiple_files_folders_without_builder(
    data_paths, datasetconfigname, builder
):
    """Ensure that datasets folders / files without ext and builder
    OR HF datasets passed via globbing pattern raises error."""
    datasetconfig = DataSetConfig(
        name=datasetconfigname, data_paths=data_paths, builder=builder
    )
    processor = get_datapreprocessor(
        processor_config=DataPreProcessorConfig(), tokenizer=None
    )
    with pytest.raises(
        # pylint: disable=c-extension-no-member
        (datasets.exceptions.DatasetNotFoundError, ValueError, pyarrow.lib.ArrowInvalid)
    ):
        processor.load_dataset(
            datasetconfig=datasetconfig,
            streaming=processor.processor_config.streaming,
            splitName="train",
            datafile=None,
        )


@pytest.mark.parametrize(
    "datafiles, datasetconfigname",
    [
        (
            [
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                ],
            ],
            DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_YAML,
        ),
    ],
)
def test_process_dataconfig_multiple_datasets_datafiles_sampling(
    datafiles, datasetconfigname
):
    """Ensure that multiple datasets with multiple files are formatted and validated correctly."""
    with open(datasetconfigname, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"] = datafiles[0]
    yaml_content["datasets"][1]["data_paths"] = datafiles[1]
    yaml_content["datasets"][2]["data_paths"] = datafiles[2]

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    TRAIN_ARGS = configs.TrainingArguments(
        packing=False,
        max_seq_length=1024,
        output_dir="tmp",
    )
    (train_set, eval_set, _, _, _, _) = process_dataargs(
        data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
    )

    assert isinstance(train_set, Dataset)
    if eval_set:
        assert isinstance(eval_set, Dataset)

    assert set(["input_ids", "attention_mask", "labels"]).issubset(
        set(train_set.column_names)
    )
    if eval_set:
        assert set(["input_ids", "attention_mask", "labels"]).issubset(
            set(eval_set.column_names)
        )
    TRAIN_ARGS.eval_strategy = "epoch"
    with pytest.raises(ValueError):
        train_set, eval_set, _, _, _, _ = process_dataargs(
            data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
        )


@pytest.mark.parametrize(
    "datafiles, datasetconfigname",
    [
        (
            [
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                ],
            ],
            DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_AND_SPLIT_YAML,
        ),
        (
            [
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                ],
                [
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                    TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                ],
            ],
            DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_AND_SPLIT_YAML_2,
        ),
    ],
)
def test_process_dataconfig_multiple_datasets_datafiles_sampling_and_split(
    datafiles, datasetconfigname
):
    """Ensure that multiple datasets with multiple files are formatted and validated correctly."""
    with open(datasetconfigname, "r") as f:
        yaml_content = yaml.safe_load(f)
    yaml_content["datasets"][0]["data_paths"] = datafiles[0]
    yaml_content["datasets"][1]["data_paths"] = datafiles[1]
    yaml_content["datasets"][2]["data_paths"] = datafiles[2]
    yaml_content["datasets"][3]["data_paths"] = datafiles[3]
    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args = configs.DataArguments(data_config_path=temp_yaml_file_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    TRAIN_ARGS = configs.TrainingArguments(
        packing=False,
        max_seq_length=1024,
        output_dir="tmp",
    )
    (train_set, eval_set, _, _, _, _) = process_dataargs(
        data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
    )

    assert isinstance(train_set, Dataset)
    assert isinstance(eval_set, Dataset)
    assert set(["input_ids", "attention_mask", "labels"]).issubset(
        set(eval_set.column_names)
    )
    # training_data_path/validation_data_path args are not supported with data_config
    with pytest.raises(ValueError):
        data_args.training_data_path = "/tmp/some/path"
        process_dataargs(
            data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
        )


@pytest.mark.parametrize(
    "data_path, test_split, train_split",
    [
        (TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET, 0.0, 1.0),
        (TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET, 0.3, 0.7),
        (TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET, 0.8, 0.2),
        (TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET, 0.8, 0.0),
    ],
)
def test_split_dataset_splits_correctly(data_path, test_split, train_split):

    dataprocessor = get_datapreprocessor(DataPreProcessorConfig(), tokenizer=None)
    dataset_config = DataSetConfig(
        name="test_dataset",
        data_paths=[data_path],
        split={"validation": test_split, "train": train_split},
    )
    d = dataprocessor.load_dataset(datasetconfig=dataset_config, streaming=False)

    if isinstance(d, (DatasetDict)):
        d = d["train"]

    n_samples = len(d)
    n_expected_test_samples = n_samples * test_split
    n_expected_train_samples = n_samples * train_split

    # split the datasets
    processed = dataprocessor.split_dataset(dataset_config, d)

    train_split = "train"
    test_split = "test"

    if n_expected_train_samples > 0:
        assert (
            train_split in processed
            and len(processed[train_split]) == n_expected_train_samples
        ), "train split should be present if split value is specified"
    if n_expected_test_samples > 0:
        assert (
            test_split in processed
            and len(processed[test_split]) == n_expected_test_samples
        ), "train split should be present if split value is specified"


@pytest.mark.parametrize(
    "data_args, is_padding_free",
    [
        # single sequence JSON and response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSON,
                validation_data_path=TWITTER_COMPLAINTS_DATA_JSON,
                dataset_text_field="output",
                response_template="\n### Label:",
            ),
            False,
        ),
        # single sequence JSONL and response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
                validation_data_path=TWITTER_COMPLAINTS_DATA_JSONL,
                dataset_text_field="output",
                response_template="\n### Label:",
            ),
            False,
        ),
        # single sequence PARQUET and response template
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_PARQUET,
                validation_data_path=TWITTER_COMPLAINTS_DATA_PARQUET,
                dataset_text_field="output",
                response_template="\n### Label:",
            ),
            False,
        ),
        # data formatter template with input/output JSON
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                data_formatter_template="### Text:{{input}} \n\n### Label: {{output}}",
                response_template="\n### Label:",
            ),
            False,
        ),
        # data formatter template with input/output JSONL
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                data_formatter_template="### Text:{{input}} \n\n### Label: {{output}}",
                response_template="\n### Label:",
            ),
            False,
        ),
        # data formatter template with input/output PARQUET
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                data_formatter_template="### Text:{{input}} \n\n### Label: {{output}}",
                response_template="\n### Label:",
            ),
            False,
        ),
        # input/output JSON with masking on input
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            ),
            False,
        ),
        # input/output JSONL with masking on input
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
            ),
            False,
        ),
        # input/output PARQUET with masking on input
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
                validation_data_path=TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            ),
            False,
        ),
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_DATA_JSON,
                validation_data_path=TWITTER_COMPLAINTS_DATA_JSON,
                dataset_text_field="output",
            ),
            True,
        ),
    ],
)
def test_process_dataargs(data_args, is_padding_free):
    """Ensure that the train/eval data are properly formatted based on the data args / text field"""
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    max_seq_length = 5
    TRAIN_ARGS = configs.TrainingArguments(
        packing=False,
        max_seq_length=max_seq_length,
        output_dir="tmp",  # Not needed but positional
    )
    (train_set, eval_set, dataset_text_field, _, _, _) = process_dataargs(
        data_args, tokenizer, TRAIN_ARGS, is_padding_free=is_padding_free
    )
    assert isinstance(train_set, Dataset)
    assert isinstance(eval_set, Dataset)
    if dataset_text_field is None:
        column_names = set(["input_ids", "attention_mask", "labels"])
        assert set(eval_set.column_names) == column_names
        assert set(train_set.column_names) == column_names
        assert len(train_set[0]["input_ids"]) == max_seq_length
    else:
        assert dataset_text_field in train_set.column_names
        assert dataset_text_field in eval_set.column_names


@pytest.mark.parametrize(
    "data_args",
    [
        # JSON pretokenized train and validation datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSON,
                validation_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSON,
            )
        ),
        # JSONL pretokenized train and validation datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
                validation_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
            )
        ),
        # PARQUET pretokenized train and validation datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
                validation_data_path=TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
            )
        ),
        # JSON pretokenized train datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSON,
            )
        ),
        # JSONL pretokenized train datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_JSONL,
            )
        ),
        # ARROW pretokenized train datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_ARROW,
            )
        ),
        # PARQUET pretokenized train datasets
        (
            configs.DataArguments(
                training_data_path=TWITTER_COMPLAINTS_TOKENIZED_PARQUET,
            )
        ),
    ],
)
def test_process_dataargs_pretokenized(data_args):
    """Ensure that pretokenized datasets are loaded and returned as is"""
    TRAIN_ARGS = configs.TrainingArguments(
        packing=False,
        max_seq_length=1024,
        output_dir="tmp",  # Not needed but positional
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    (train_set, eval_set, _, _, _, _) = process_dataargs(
        data_args, tokenizer, TRAIN_ARGS
    )
    assert isinstance(train_set, Dataset)
    if eval_set:
        assert isinstance(eval_set, Dataset)

    assert set(["input_ids", "labels"]).issubset(set(train_set.column_names))
    if eval_set:
        assert set(["input_ids", "labels"]).issubset(set(eval_set.column_names))


@pytest.mark.parametrize(
    "datafile, column_names, datasetconfigname",
    [
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            set(["ID", "Label", "input", "output"]),
            "text_dataset_input_output_masking",
        ),
        (
            TWITTER_COMPLAINTS_TOKENIZED_JSON,
            set(
                [
                    "Tweet text",
                    "ID",
                    "Label",
                    "text_label",
                    "output",
                    "input_ids",
                    "labels",
                    "attention_mask",
                ]
            ),
            "pretokenized_dataset",
        ),
        (
            TWITTER_COMPLAINTS_DATA_JSON,
            set(["Tweet text", "ID", "Label", "text_label", "output"]),
            "apply_custom_data_template",
        ),
    ],
)
def test_process_dataset_configs(datafile, column_names, datasetconfigname):
    """Test process_dataset_configs for expected output."""
    dataprocessor_config = DataPreProcessorConfig()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    processor = DataPreProcessor(
        processor_config=dataprocessor_config,
        tokenizer=tokenizer,
    )
    datasetconfig = [DataSetConfig(name=datasetconfigname, data_paths=[datafile])]
    train_dataset, _ = processor.process_dataset_configs(dataset_configs=datasetconfig)

    assert isinstance(train_dataset, Dataset)
    assert set(train_dataset.column_names) == column_names

    with open(datafile, "r") as file:
        data = json.load(file)
    assert len(train_dataset) == len(data)


@pytest.mark.parametrize(
    "datafiles, sampling, datasetconfigname",
    [
        (
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            ],
            [0.3, None, 0.3],
            DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_YAML,
        ),
        (
            [
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_ARROW,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSONL,
                TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_PARQUET,
            ],
            [0.3, 0.5, 0.3],
            DATA_CONFIG_MULTIPLE_DATASETS_SAMPLING_YAML,
        ),
    ],
)
def test_process_dataset_configs_with_sampling_error(
    datafiles, sampling, datasetconfigname
):
    """
    Ensure that if sampling ratios aren't correctly
    passed (don't add up to 1.0), error is raised
    """
    data_args = configs.DataArguments()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    TRAIN_ARGS = configs.TrainingArguments(
        packing=False,
        max_seq_length=1024,
        output_dir="tmp",  # Not needed but positional
    )

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        with open(datasetconfigname, "r") as f:
            data = yaml.safe_load(f)
            _dataset = data["datasets"]
            for i, d in enumerate(_dataset):
                d["data_paths"][0] = datafiles[i]
                d["sampling"] = sampling[i]
            yaml.dump(data, temp_yaml_file)
        data_args.data_config_path = temp_yaml_file.name

    with pytest.raises(ValueError):
        (_, _, _, _, _, _) = process_dataargs(
            data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
        )


@pytest.mark.parametrize(
    "datafile, rename, select, final, datasetconfigname",
    [
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            {"input": "instruction", "output": "response"},
            None,
            ["ID", "Label", "instruction", "response"],
            DATA_CONFIG_RENAME_SELECT_COLUMNS,
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            None,
            ["ID", "input", "output"],
            ["ID", "input", "output"],
            DATA_CONFIG_RENAME_SELECT_COLUMNS,
        ),
        (
            TWITTER_COMPLAINTS_DATA_INPUT_OUTPUT_JSON,
            {"input": "instruction", "output": "response"},
            ["Label", "instruction", "response"],
            ["Label", "instruction", "response"],
            DATA_CONFIG_RENAME_SELECT_COLUMNS,
        ),
    ],
)
def test_rename_and_select_dataset_columns(
    datafile, rename, select, final, datasetconfigname
):
    """Test process_dataset_configs for expected output."""
    dataprocessor_config = DataPreProcessorConfig()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    processor = DataPreProcessor(
        processor_config=dataprocessor_config,
        tokenizer=tokenizer,
    )

    handlers = []
    if rename:
        handlers.append(
            DataHandlerConfig(
                name="rename_columns",
                arguments={"column_mapping": rename},
            )
        )
    if select:
        handlers.append(
            DataHandlerConfig(name="select_columns", arguments={"column_names": select})
        )
    data_paths = [datafile]

    datasetconfig = [
        DataSetConfig(
            name=datasetconfigname, data_paths=data_paths, data_handlers=handlers
        )
    ]
    train_dataset, _ = processor.process_dataset_configs(dataset_configs=datasetconfig)

    assert isinstance(train_dataset, Dataset)
    assert set(train_dataset.column_names) == set(final)

    with open(datafile, "r", encoding="utf-8") as file:
        data = json.load(file)
    assert len(train_dataset) == len(data)


@pytest.mark.parametrize(
    "datafile, datasetconfigname",
    [
        (
            CHAT_DATA_SINGLE_TURN,
            DATA_CONFIG_MULTITURN_DATA_YAML,
        ),
        (
            CHAT_DATA_MULTI_TURN,
            DATA_CONFIG_MULTITURN_DATA_YAML,
        ),
    ],
)
def test_process_datasets_offline(datafile, datasetconfigname):
    """
    Ensure functions in offline_data_preprocessing script,
    process_datasets_offline and save_dataset_shards process
    and saves the formatted dataset correctly.
    """

    data_args = configs.DataArguments()
    MODEL_ARGS = configs.ModelArguments(
        model_name_or_path=MODEL_NAME, use_flash_attn=False
    )
    data_args.dataset_text_field = "formatted_text"
    columns = [data_args.dataset_text_field]

    data_args.do_dataprocessing_only = True
    data_args.num_train_dataset_shards = num_dataset_shards = 2

    with open(datasetconfigname, "r", encoding="utf-8") as f:
        yaml_content = yaml.safe_load(f)
        d = [
            {
                "data_paths": [datafile],
                "data_handlers": [
                    {
                        "name": "apply_tokenizer_chat_template",
                        "arguments": {
                            "fn_kwargs": {
                                "formatted_text_column_name": data_args.dataset_text_field
                            },
                            "batched": False,
                            "remove_columns": "all",
                        },
                    }
                ],
            }
        ]
        yaml_content["datasets"] = d

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".yaml"
    ) as temp_yaml_file:
        yaml.dump(yaml_content, temp_yaml_file)
        temp_yaml_file_path = temp_yaml_file.name
        data_args.data_config_path = temp_yaml_file_path

    with tempfile.TemporaryDirectory() as tmpdirname:
        TRAIN_ARGS = configs.TrainingArguments(
            output_dir=tmpdirname, max_seq_length=4096
        )

        tokenizer = AutoTokenizer.from_pretrained(MODEL_ARGS.model_name_or_path)

        formatted_train_dataset, _, _, _, _, _ = process_dataargs(
            data_args=data_args, tokenizer=tokenizer, train_args=TRAIN_ARGS
        )

        assert isinstance(formatted_train_dataset, Dataset)
        assert set(formatted_train_dataset.column_names) == set(columns)
        with open(datafile, encoding="utf-8") as f:
            assert len(formatted_train_dataset) == sum(1 for _ in f)

        train_dataset_dir = os.path.join(TRAIN_ARGS.output_dir, "train_dataset")
        assert len(os.listdir(train_dataset_dir)) == num_dataset_shards


@pytest.mark.parametrize(
    "model_name",
    [TINY_LLAMA_VISION_MODEL_NAME, TINY_GRANITE_VISION_MODEL_NAME],
)
def test_vision_data_collator(model_name):
    """Test the VisionDataCollator with dummy Image data."""

    processor = AutoProcessor.from_pretrained(model_name)
    collator = VisionDataCollator(processor)
    processor_kwargs = {}
    processor_kwargs["return_tensors"] = "pt"
    processor_kwargs["padding"] = True

    with open(IMAGE_DATASET, "r", encoding="utf-8") as f:
        image_data = [json.loads(line) for line in f]
    features = []
    processor_kwargs = {}
    processor_kwargs["return_tensors"] = "pt"
    processor_kwargs["padding"] = True

    # Make supported format features with PIL Image
    for data in image_data:
        pil_image = Image.fromarray(np.array(data["image"], dtype=np.uint8))
        features.append(
            {
                "processor_kwargs": processor_kwargs,
                "fields_name": {
                    "dataset_text_field": "text",
                    "dataset_image_field": "image",
                },
                "text": data["text"],
                "image": [pil_image],
            }
        )

    # Call the collator which returns a batch dictionary containing "input_ids" and "labels"
    batch = collator(features)

    assert "input_ids" in batch
    assert "labels" in batch
    assert "attention_mask" in batch
    assert batch["input_ids"].shape == batch["labels"].shape
