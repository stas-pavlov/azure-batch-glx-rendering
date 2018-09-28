# Move GLX rendering from container on new level running its in Azure Batch

## Intro
Here https://github.com/stas-pavlov/azureglxrendering we've created Ububntu VM wich can run NVIDIA containers to render OpenGL on host X server. But normally you would like to automate VMs and rendering task management to optimize costs and minimize manual work. Good news, that there is a good solution for those task in Azure -- Azure Batch https://azure.microsoft.com/en-us/services/batch/.
You have 2 options to run task with custom images on Azure Batch:
1. create custome image and use it
2. use startup script to setup all needed stuff on standard VM

Normally, first options is much more simple and you can mark your image as containre supported and use API for container scheduling directly. So if you decided to use a custom image, just prepare it using https://github.com/stas-pavlov/azureglxrendering tutorial and then genralase and prepare for use as a base one.

We will focus on second option as it much more flexible and can give you ideas how to create you own solution.

## Create Azure Batch account
Let's start from creating Azure Batch account. As usual I use Azure CLI, you can use Azure Portal or any other ways to do it.
```
az group create -n azurebatchrendering-rg -l eastus
az storage account create -n batchrenderingstorage -g azurebatchrendering-rg -l eastus --sku Standard_LRS
az batch account create -n glxrendering -g azurebatchrendering-rg -l eastus --storage-account batchrenderingstorage
```
So we created Azure Batch glxrendering.eastus.batch.azure.com
To write automation we need keys for Azure Batch and Azure Storage accounts we created:
```
az batch account keys list -n glxrendering -g azurebatchrendering-rg
az storage account keys list -n batchrenderingstorage -g azurebatchrendering-rg
```
Store output of this commands to use in automation script.

## Automate Azure Bacth pool, job and task creation
We will use Python with Azure Batch SDK for Python to automate Azure Bacth pool creation. So we use Ubuntu Server 16.04-LTS as a base and add startup task, based on script from https://github.com/stas-pavlov/azureglxrendering. You can find in scripts folder of the repository (init-vm-glx-rendering.sh).
```
new_pool = batch.models.PoolAddParameter(
        id=pool_id,
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=batch.models.ImageReference(
                publisher='Canonical',
                offer='UbuntuServer',
                sku='16.04-LTS',
                version='latest'),
        node_agent_sku_id="batch.node.ubuntu 16.04"
        ),
        vm_size=_POOL_VM_SIZE,
        target_dedicated_nodes=_POOL_NODE_COUNT,
        max_tasks_per_node=2,
        start_task=batchmodels.StartTask(
            command_line="./init-vm-glx-rendering.sh",
            resource_files=startup_files,
            user_identity=batchmodels.UserIdentity(auto_user=batchmodels.AutoUserSpecification(scope='task', elevation_level='admin')),
            wait_for_success=True
        )
    )
    batch_service_client.pool.add(new_pool)
```

So we need to copy this script to a node to run, so we need to add resource files to our task and put files on a Azure Storage. So start from function to upload a local file to an Azure Blob storage container and return a ResourceFile initialized with a SAS URL appropriate for Batch tasks.

```
def upload_file_to_container(block_blob_client, container_name, file_path):
    """
    Uploads ala loc file to an Azure Blob storage container.

    :param block_blob_client: A blob service client.
    :type block_blob_client: `azure.storage.blob.BlockBlobService`
    :param str container_name: The name of the Azure Blob storage container.
    :param str file_path: The local path to the file.
    :rtype: `azure.batch.models.ResourceFile`
    :return: A ResourceFile initialized with a SAS URL appropriate for Batch
    tasks.
    """
    blob_name = os.path.basename(file_path)

    print('Uploading file {} to container [{}]...'.format(file_path,
                                                          container_name))

    block_blob_client.create_blob_from_path(container_name,
                                            blob_name,
                                            file_path)

    sas_token = block_blob_client.generate_blob_shared_access_signature(
        container_name,
        blob_name,
        permission=azureblob.BlobPermissions.READ,
        expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=2))

    sas_url = block_blob_client.make_blob_url(container_name,
                                              blob_name,
                                              sas_token=sas_token)

    return batchmodels.ResourceFile(file_path=blob_name,
                                    blob_source=sas_url,
                                    file_mode="777")
```
And use it to create resource files to use during the pool creation
```
blob_client = azureblob.BlockBlobService(
        account_name=_STORAGE_ACCOUNT_NAME,
        account_key=_STORAGE_ACCOUNT_KEY)

scripts_container_name = 'scripts'
blob_client.create_container(scripts_container_name, fail_on_exist=False)

startup_file_paths = [os.path.join('scripts', 'init-vm-glx-rendering.sh')]

startup_files = [
    upload_file_to_container(blob_client, scripts_container_name, file_path)
    for file_path in startup_file_paths]
```
Ok, so now we've created the pool, so we need to create a job and add a task to the job.
Create a job
```
    job = batch.models.JobAddParameter(
        id=job_id,
        pool_info=batch.models.PoolInformation(pool_id=pool_id)
    )

    batch_service_client.job.add(job)
```
Add task
```
command_line = 'bash -c "sudo docker run --runtime=nvidia -i --rm -e "DISPLAY=:0" -v /tmp/.X11-unix:/tmp/.X11-unix stasus/glxgears"'
    task = batch.models.TaskAddParameter(
            id=task_name,
            command_line=command_line,
            user_identity=batchmodels.UserIdentity(auto_user=batchmodels.AutoUserSpecification(scope='task', elevation_level='admin'))
        )

    batch_service_client.task.add(job_id, task)
```
You can see that we use the same command to run the task as for https://github.com/stas-pavlov/azureglxrendering. The only change that I've created the test contaier and put it to the Docker Hub, so you can simple use it stasus/glxgears. If you prefer to use prvate docker repository you need to login before use, so just add docker login command separated by coma before docker run.

You can find full code at this repo in create-render-task.py, it works fine in Visual Studio code, you can run it section by section and create as many tasks as you want to test. Please note, that each task in a job must have unique name, so just change it manually.


