"""
Training entrypoint for WaveRNN.
"""
import os
import shutil
from typing import List, Optional

import click
import pytorch_lightning as pl
import torch
from omegaconf import OmegaConf
from pytorch_lightning.loggers import TensorBoardLogger

from wavernn.dataset import AudioDataModule
from wavernn.model import VALIDATION_LOSS_KEY, Config, ExportableWaveRNN, Model
from wavernn.util import die_if

# Constants related to the model directory organization.
#
# A model directory contains everything associated with a single model. This
# includes the model config (config.yaml), the checkpoints directory
# (checkpoints) with the best checkpoint (best.ckpt) in it, a logs directory
# for Tensorboard logs, and anything else the model may need. All operations
# with models are done by passing a --path argument pointing to a model directory.

# Name of the config file to store.
CONFIG_PATH: str = "config.yaml"

# Where to store checkpoints.
CHECKPOINTS_DIR: str = "checkpoints"

# Where to write best checkpoint.
BEST_CHECKPOINT: str = "best"


@click.command("train")
@click.option(
    "--config", type=click.Path(exists=True, dir_okay=False), help="YAML model config"
)
@click.option(
    "--path", required=True, type=click.Path(file_okay=False), help="Model directory"
)
@click.option(
    "--data", required=True, type=click.Path(file_okay=False), help="Dataset directory"
)
@click.option(
    "--test-every", default=5000, help="How often to run validation during training"
)
@click.option(
    "--initial-weights",
    type=click.Path(exists=True, dir_okay=False),
    help="Checkpoint to load as the initial weights",
)
@click.argument("overrides", nargs=-1)
def train(  # pylint: disable=missing-param-doc
    config: Optional[str],
    path: str,
    data: str,
    test_every: int,
    initial_weights: Optional[str],
    overrides: List[str],
) -> None:
    """
    Train a WaveRNN.
    """
    die_if(
        config is None and not os.path.exists(path),
        f"Since --config is not passed, directory {path} must exist",
    )

    # If this is the first time a model is being trained, create its directory
    # and populate it with a config file. Otherwise, use the existing
    # directory and the existing config file.
    saved_config_path = os.path.join(path, CONFIG_PATH)
    if config is None or os.path.exists(saved_config_path):
        config = saved_config_path
        die_if(not os.path.exists(config), f"Missing config file {config}")
    else:
        os.makedirs(path, exist_ok=True)
        shutil.copyfile(config, saved_config_path)

    # Create a model with the config.
    model_config: Config = OmegaConf.structured(Config)
    model_config.merge_with(OmegaConf.load(config))  # type: ignore
    model_config.merge_with_dotlist(overrides)  # type: ignore
    model = Model(model_config)

    # Load the dataset from the config.
    data_module = AudioDataModule(data, model_config.data)

    last_path = os.path.join(path, CHECKPOINTS_DIR, "last.ckpt")
    if initial_weights is not None:
        model = Model.load_from_checkpoint(initial_weights, config=model_config)
        resume_from: Optional[str] = None
    elif os.path.exists(last_path):
        model = Model.load_from_checkpoint(last_path, config=model_config)
        resume_from = last_path
    else:
        # If this model has never been initialized before, compute the input
        # stats from the dataset. The input stats are used for normalizing the
        # input features. Doing this on the first run makes our model less
        # error-prone, as it is impossible to set an incorrect feature
        # normalization.
        model = Model(model_config)
        data_module.setup(stage="fit")
        model.initialize_input_stats(data_module.train_dataloader())
        resume_from = None

    # Train the model. Even though we have loaded the model already, we still
    # need to resume from the last checkpoint, otherwise global_step isn't
    # correctly set.
    checkpoint_callback = pl.callbacks.ModelCheckpoint(
        monitor=VALIDATION_LOSS_KEY,
        dirpath=os.path.join(path, CHECKPOINTS_DIR),
        filename=BEST_CHECKPOINT,
        mode="min",
        save_last=True,
    )
    logger = TensorBoardLogger(save_dir=path, version="logs", name=None)
    trainer = pl.Trainer(
        callbacks=[checkpoint_callback],
        val_check_interval=test_every,
        logger=logger,
        accelerator="auto",
        devices=1
    )
    trainer.fit(model, data_module, ckpt_path=resume_from)


@click.command("export")
@click.option(
    "--path", required=True, type=click.Path(file_okay=False), help="Model directory"
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False),
    help="Path to export to",  # pylint: disable=missing-param-doc
)
def export(path: str, output: str) -> None:
    """
    Export a trained WaveRNN.
    """
    config = os.path.join(path, CONFIG_PATH)
    die_if(not os.path.exists(config), f"Missing config file {config}")

    last_path = os.path.join(path, CHECKPOINTS_DIR, "last.ckpt")
    die_if(not os.path.exists(last_path), f"Missing checkpoint {last_path}")

    model_config: Config = OmegaConf.structured(Config)
    model_config.merge_with(OmegaConf.load(config))  # type: ignore
    model = Model.load_from_checkpoint(last_path, config=model_config)

    exported = torch.jit.script(ExportableWaveRNN(model))
    exported.save(output)
