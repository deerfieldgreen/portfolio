"""Standard training loop with early stopping."""
import numpy as np
from typing import Optional, Dict, Callable


class EarlyStopping:
    """Early stopping tracker."""

    def __init__(self, patience: int = 10, min_delta: float = 1e-4):
        self.patience = patience
        self.min_delta = min_delta
        self.best_loss = np.inf
        self.counter = 0

    def should_stop(self, val_loss: float) -> bool:
        if val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.counter = 0
            return False
        self.counter += 1
        return self.counter >= self.patience


def train_pytorch_model(
    model,
    train_loader,
    val_loader,
    optimizer,
    criterion,
    epochs: int = 50,
    patience: int = 10,
    device: str = "cpu",
) -> Dict:
    """
    Standard PyTorch training loop with early stopping.
    Returns dict with train_losses, val_losses, best_epoch, epochs_trained.
    """
    import torch

    early_stop = EarlyStopping(patience=patience)
    train_losses = []
    val_losses = []
    best_state = None
    best_epoch = 0

    for epoch in range(epochs):
        # Train
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for X_batch, y_batch in train_loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred.squeeze(), y_batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1
        train_loss = epoch_loss / max(n_batches, 1)
        train_losses.append(train_loss)

        # Validate
        model.eval()
        val_loss = 0.0
        n_val = 0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch = X_batch.to(device)
                y_batch = y_batch.to(device)
                pred = model(X_batch)
                loss = criterion(pred.squeeze(), y_batch)
                val_loss += loss.item()
                n_val += 1
        val_loss = val_loss / max(n_val, 1)
        val_losses.append(val_loss)

        if val_loss < early_stop.best_loss:
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            best_epoch = epoch

        if early_stop.should_stop(val_loss):
            break

    # Restore best model
    if best_state:
        model.load_state_dict(best_state)

    return {
        "train_losses": train_losses,
        "val_losses": val_losses,
        "best_epoch": best_epoch,
        "epochs_trained": len(train_losses),
        "train_val_gap": train_losses[-1] - val_losses[-1] if train_losses else 0,
    }
