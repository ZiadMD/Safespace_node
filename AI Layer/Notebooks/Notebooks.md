# Notebooks
## notebooks is for training and testing AI models used in Safespace.
The trained models are stored in the `Models` directory.
The Datasets used for training are stored in the `Datasets` directory.
The new datasets are stored in the `Datasets` directory.

## Usage
1. Open the desired notebook in Jupyter or any compatible environment.
2. Follow the instructions in the notebook to train or test the AI models.
3. Save the trained models to the `Models` directory for use in the Safespace

```python
from ultralytics import YOLO
TRAINING_CONFIG = {
    'data': r"path/to/data.yaml",                         # Path to data.yaml
    'epochs': 40,                                         # Number of training epochs
    'batch': 16,                                          # Batch size (adjust based on GPU memory)
    'imgsz': 640,                                         # Image size
    'device': 0 if torch.cuda.is_available() else 'cpu',  # GPU device or CPU
    'workers': 8,                                         # Number of data loading workers
    'patience': 20,                                       # Early stopping patience
    'save': True,                                         # Save checkpoints
    'project': 'Models',                                  # Project directory (keep as 'Models')
    'name': 'Model_Name',                                 # Experiment name
    'exist_ok': True,                                     # Overwrite existing experiment
    'pretrained': True,                                   # Use pretrained weights
    'optimizer': 'auto',                                  # Optimizer (auto, SGD, Adam, AdamW, etc.)
    'verbose': True,                                      # Verbose output
    'seed': 42,                                           # Random seed for reproducibility
    'val': True,                                          # Validate during training
    'plots': True,                                        # Generate training plots
}

model = YOLO('yolov8n.pt')  # Load a pre-trained YOLOv8n model
model.train(**TRAINING_CONFIG)

```

## Other Usage
used to make new datasets for training the AI models.


** Don't delete the notebooks after training; they are useful for future reference. **