import numpy as np 
import os
from PIL import Image
import cv2
from torchvision import transforms
from torch.utils.tensorboard import SummaryWriter
import torch
from argparse import ArgumentParser 
import json
from tqdm import tqdm
from efficientnet_pytorch import EfficientNet
from melanoma_cnn_efficientnet import Net
from pathlib import Path
# import tensorflow as tf

def select_n_random(data, labels, n=100):
    '''
    Selects n random datapoints and their corresponding labels from a dataset
    '''
    assert len(data) == len(labels)

    perm = torch.randperm(len(data))
    return data[perm][:n], labels[perm][:n]

parser = ArgumentParser()
parser.add_argument("--use_cnn", action='store_true', help='retrieve features from the last layer of EfficientNet B2')
parser.add_argument("--sprite", action='store_true')
args = parser.parse_args()


# Setting up GPU for processing or CPU if GPU isn't available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

transform = transforms.ToTensor()
testing_transforms = transforms.Compose([transforms.Resize(256),
                                            transforms.CenterCrop(256),
                                            transforms.ToTensor(),
                                            transforms.Normalize([0.485, 0.456, 0.406], 
                                                                [0.229, 0.224, 0.225])])

if args.use_cnn:
    directories = ["/workspace/stylegan2-ada-pytorch/processed_dataset_256_SAM", "/workspace/stylegan2-ada-pytorch/processed_dataset_256"]
    filename = "dataset.json"

    arch = EfficientNet.from_pretrained('efficientnet-b2')
    model = Net(arch=arch, return_feats=True)  
    model.load_state_dict(torch.load('/workspace/stylegan2-ada-pytorch/CNN_trainings/melanoma_model_0_0.9225_16_12_train_reals+15melanoma.pth'))
    model.eval()
    model.to(device)
    images_pil = []
    metadata_f = [] 
    embeddings = []
    for directory in directories:
        with open(os.path.join(directory, filename)) as file:
            data = json.load(file)['labels']
            with torch.no_grad():
                for img, label in tqdm(data):
                    img_dir = os.path.join(directory,img) 
                    img_net = torch.tensor(testing_transforms(Image.open(img_dir)).unsqueeze(0), dtype=torch.float32).to(device)
                    emb = model(img_net)
                    embeddings.append(emb.cpu())                
                    metadata_f.append(['4', img] if directory.split('/')[-1] == "processed_dataset_256_SAM"
                                                else [label, img])  # to discern between SAM data and the rest
                    if args.sprite:
                        img_pil = transform(Image.open(img_dir).resize((100, 100)))
                        images_pil.append(img_pil)

    # Repeat the process for randomly generated data
    images = [str(f) for f in sorted(Path("/workspace/stylegan2-ada-pytorch/projector/generated-20kpkl7").rglob('*jpg')) if os.path.isfile(f)]
    labels = [2 if f.split('.jpg')[0][-1] == '0' else 3 for f in images]
    with torch.no_grad():
        for img_dir, label in tqdm(zip(images, labels)):
            img_net = torch.tensor(testing_transforms(Image.open(img_dir)).unsqueeze(0), dtype=torch.float32).to(device)
            emb = model(img_net)
            embeddings.append(emb.cpu())                
            metadata_f.append([label, img]) 
            if args.sprite:
                img_pil = transform(Image.open(img_dir).resize((100, 100)))
                images_pil.append(img_pil)

    embeddings_tensor = torch.stack(embeddings).squeeze()
    if args.sprite:
        images_pil = torch.stack(images_pil)
    # default `log_dir` is "runs" - we'll be more specific here
    writer = SummaryWriter('/workspace/stylegan2-ada-pytorch/CNN_embeddings_projector/sam_synt_isic') 
        
else:
    # This part can be used with G_mapping embeddings (vector w) - projections in the latent space
    directory = "/workspace/stylegan2-ada-pytorch/projector/generated-20kpkl7"   
    emb_f = "allvectors.txt"
    metadata_f = "alllabelsf.txt"
    transform = transforms.ToTensor()

    with open(os.path.join(directory, emb_f)) as f:
        embeddings = f.readlines() #[::2]
    embeddings_tensor = torch.tensor( [float(i) for emb_line in embeddings for i in emb_line[:-2].split(' ') ] ).reshape(len(embeddings),-1)


    with open(os.path.join(directory, metadata_f)) as f:
        metadata=f.readlines() #[::2]
    metadata_f = [[name.split('.')[0].split(' ')[0], name.split('.')[0].split(' ')[1]] for name in metadata]

    images_pil = torch.empty(len(metadata), 3, 100,100)
    labels = []
    for i, line in enumerate(metadata):
        label = line.split(' ')[0]
        img_name = line.split(' ')[1].split('txt')[0] + 'from.png'  # 0 img00000552.class.0.txt 
                #line.split(' ')[1].split('.')[0] + '_' + label + '.png'    
        img_dir = os.path.join(directory,img_name)
        img = transform(Image.open(img_dir).resize((100, 100))) 
        images_pil[i] = img
        labels.append(label)

    # default `log_dir` is "runs" - we'll be more specific here
    writer = SummaryWriter('/workspace/stylegan2-ada-pytorch/projector' + directory.split('/')[-1]) #('/home/stylegan2-ada-pytorch/projector') #('/workspace/melanoma_isic_dataset/stylegan2-ada-pytorch/projector')

if args.sprite:
    writer.add_embedding(embeddings_tensor, 
                    metadata=metadata_f,
                    metadata_header=["label","image_name"],
                    label_img=images_pil)
else:
    writer.add_embedding(embeddings_tensor, 
                    metadata=metadata_f,
                    metadata_header=["label","image_name"])
writer.close() 