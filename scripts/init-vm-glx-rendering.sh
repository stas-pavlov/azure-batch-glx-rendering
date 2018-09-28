#!/bin/bash 

# install NVIDIA Driver
CUDA_REPO_PKG=cuda-repo-ubuntu1604_9.1.85-1_amd64.deb
wget -O /tmp/${CUDA_REPO_PKG} http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/${CUDA_REPO_PKG} 
sudo dpkg -i /tmp/${CUDA_REPO_PKG}
sudo apt-key adv --fetch-keys http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/7fa2af80.pub 
rm -f /tmp/${CUDA_REPO_PKG}
sudo apt-get update -y
sudo apt-get install cuda-drivers -y

# install docker-ce
sudo apt-get update -y
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo apt-key fingerprint 0EBFCD88
sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable"
sudo apt-get update -y
sudo apt-get install docker-ce -y

# install nvidia-docker2
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey|sudo apt-key add -
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list|sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update -y
sudo apt-get install nvidia-docker2 -y
sudo pkill -SIGHUP dockerd

# install X server if needed
sudo apt-get update -y
sudo apt-get install xinit -y
sudo apt-get install xserver-xorg-legacy -y

# config X server to use GPU
sudo nvidia-xconfig --busid `nvidia-xconfig --query-gpu-info | grep BusID | sed 's/PCI BusID : PCI:/PCI:/'`
sudo sed -i 's/console/anybody/g'  /etc/X11/Xwrapper.config

# start X server with disabled authentication
X :0 -ac&

exit