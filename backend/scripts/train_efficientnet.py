"""Train Stage 2 EfficientNet-B0 on the cleaned ImageFolder dataset.

RTX 4050/6 GB defaults: 224px, batch 32, AMP, workers 0 on Windows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, models, transforms


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data', default='data/dataset/classifier'); p.add_argument('--epochs',type=int,default=30)
    p.add_argument('--batch',type=int,default=32); p.add_argument('--imgsz',type=int,default=224)
    p.add_argument('--workers',type=int,default=0); p.add_argument('--lr',type=float,default=3e-4)
    p.add_argument('--out',default='outputs/efficientnet'); p.add_argument('--device',default='0')
    args=p.parse_args(); device=torch.device('cuda:'+args.device if torch.cuda.is_available() else 'cpu')
    mean,std=[.485,.456,.406],[.229,.224,.225]
    tr=transforms.Compose([transforms.RandomResizedCrop(args.imgsz,scale=(.7,1)),transforms.RandomHorizontalFlip(),transforms.ColorJitter(.25,.25,.25,.05),transforms.ToTensor(),transforms.Normalize(mean,std)])
    va=transforms.Compose([transforms.Resize(int(args.imgsz*1.15)),transforms.CenterCrop(args.imgsz),transforms.ToTensor(),transforms.Normalize(mean,std)])
    root=Path(args.data); train_ds=datasets.ImageFolder(root/'train',transform=tr); val_ds=datasets.ImageFolder(root/'val',transform=va)
    counts=torch.bincount(torch.tensor(train_ds.targets),minlength=len(train_ds.classes)); weights=[1.0/max(1,counts[y].item()) for y in train_ds.targets]
    sampler=WeightedRandomSampler(weights,len(weights),replacement=True)
    kw=dict(num_workers=args.workers,pin_memory=device.type=='cuda'); train_dl=DataLoader(train_ds,batch_size=args.batch,sampler=sampler,**kw); val_dl=DataLoader(val_ds,batch_size=args.batch,shuffle=False,**kw)
    model=models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1); model.classifier[1]=nn.Linear(model.classifier[1].in_features,len(train_ds.classes)); model.to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=1e-4); sched=torch.optim.lr_scheduler.CosineAnnealingLR(opt,args.epochs); loss_fn=nn.CrossEntropyLoss(label_smoothing=.1); scaler=torch.amp.GradScaler('cuda',enabled=device.type=='cuda')
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); (out/'class_mapping.json').write_text(json.dumps({i:c for i,c in enumerate(train_ds.classes)},indent=2))
    best=0
    for epoch in range(1,args.epochs+1):
        model.train(); total=correct=running=0
        for x,y in train_dl:
            x,y=x.to(device,non_blocking=True),y.to(device,non_blocking=True); opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type='cuda',dtype=torch.float16,enabled=device.type=='cuda'): z=model(x); loss=loss_fn(z,y)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); running+=loss.item()*y.size(0); correct+=(z.argmax(1)==y).sum().item(); total+=y.size(0)
        model.eval(); vc=vt=vl=0
        with torch.no_grad():
            for x,y in val_dl:
                x,y=x.to(device,non_blocking=True),y.to(device,non_blocking=True)
                with torch.autocast(device_type='cuda',dtype=torch.float16,enabled=device.type=='cuda'): z=model(x); l=loss_fn(z,y)
                vl+=l.item()*y.size(0); vc+=(z.argmax(1)==y).sum().item(); vt+=y.size(0)
        sched.step(); acc=100*vc/max(1,vt); print(f'Epoch {epoch}/{args.epochs} train_loss={running/max(1,total):.4f} train_acc={100*correct/max(1,total):.2f}% val_loss={vl/max(1,vt):.4f} val_acc={acc:.2f}%')
        ck={'epoch':epoch,'model_state_dict':model.state_dict(),'optimizer_state_dict':opt.state_dict(),'val_acc':acc,'classes':train_ds.classes}
        torch.save(ck,out/'last.pt')
        if acc>best: best=acc; torch.save(ck,out/'best.pt')
    print(f'best={best:.2f}% weights={out/"best.pt"}')
if __name__=='__main__': main()
