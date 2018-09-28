#%% imports
import os
import datetime
import azure.storage.blob as azureblob
import azure.batch.batch_service_client as batch
import azure.batch.batch_auth as batchauth
import azure.batch.models as batchmodels

#%% globals
_BATCH_ACCOUNT_NAME ="<batch_account_name>"
_BATCH_ACCOUNT_KEY = "<batch_account_key>"
_BATCH_ACCOUNT_URL = "<batch_account_url>"
_STORAGE_ACCOUNT_NAME = "<storage_account_name>"
_STORAGE_ACCOUNT_KEY = "<storage_account_key>"
_POOL_ID = 'glxgears_pool'
_POOL_NODE_COUNT = 2
_POOL_VM_SIZE = 'STANDARD_NV6'
_JOB_ID = 'glxgears_test'

#%% common declarations
def print_batch_exception(batch_exception):
    """
    Prints the contents of the specified Batch exception.

    :param batch_exception:
    """
    print('-------------------------------------------')
    print('Exception encountered:')
    if batch_exception.error and \
            batch_exception.error.message and \
            batch_exception.error.message.value:
        print(batch_exception.error.message.value)
        if batch_exception.error.values:
            print()
            for mesg in batch_exception.error.values:
                print('{}:\t{}'.format(mesg.key, mesg.value))
    print('-------------------------------------------')

#%% upload files to container
def upload_file_to_container(block_blob_client, container_name, file_path):
    """
    Uploads a local file to an Azure Blob storage container.

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

blob_client = azureblob.BlockBlobService(
        account_name=_STORAGE_ACCOUNT_NAME,
        account_key=_STORAGE_ACCOUNT_KEY)

scripts_container_name = 'scripts'
blob_client.create_container(scripts_container_name, fail_on_exist=False)

startup_file_paths = [os.path.join('scripts', 'init-vm-glx-rendering.sh')]

startup_files = [
    upload_file_to_container(blob_client, scripts_container_name, file_path)
    for file_path in startup_file_paths]

#%% create pool
def create_pool(batch_service_client, pool_id):
    """
    Creates a pool of compute nodes with the specified OS settings.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str pool_id: An ID for the new pool.
    :param str publisher: Marketplace image publisher
    :param str offer: Marketplace image offer
    :param str sku: Marketplace image sky
    """
    print('Creating pool [{}]...'.format(pool_id))

    # Create a new pool of Linux compute nodes using an Azure Virtual Machines
    # Marketplace image. For more information about creating pools of Linux
    # nodes, see:
    # https://azure.microsoft.com/documentation/articles/batch-linux-nodes/ё

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
    
credentials = batchauth.SharedKeyCredentials(_BATCH_ACCOUNT_NAME,
                                             _BATCH_ACCOUNT_KEY)

batch_client = batch.BatchServiceClient(
        credentials,
        base_url=_BATCH_ACCOUNT_URL)

try:
    create_pool(batch_client, _POOL_ID)
except batchmodels.BatchErrorException as err:
    print_batch_exception(err)
    raise


#%% create job
def create_job(batch_service_client, job_id, pool_id):
    """
    Creates a job with the specified ID, associated with the specified pool.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str job_id: The ID for the job.
    :param str pool_id: The ID for the pool.
    """
    print('Creating job [{}]...'.format(job_id))

    job = batch.models.JobAddParameter(
        id=job_id,
        pool_info=batch.models.PoolInformation(pool_id=pool_id)
    )

    batch_service_client.job.add(job)

try:
    create_job(batch_client, _JOB_ID, _POOL_ID)
except batchmodels.BatchErrorException as err:
    print_batch_exception(err)
    raise

#%% create rendering task
def add_tasks(batch_service_client, job_id, task_name):
    """
    Adds a task for each input file in the collection to the specified job.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str job_id: The ID of the job to which to add the tasks.
    :param list input_files: A collection of input files. One task will be
     created for each input file.
    :param output_container_sas_token: A SAS token granting write access to
    the specified Azure Blob storage container.
    """

    print('Adding task [{}] to job [{}]...'.format(task_name, job_id))

    command_line = 'bash -c "sudo docker run --runtime=nvidia -i --rm -e "DISPLAY=:0" -v /tmp/.X11-unix:/tmp/.X11-unix stasus/glxgears"'
    task = batch.models.TaskAddParameter(
            id=task_name,
            command_line=command_line,
            user_identity=batchmodels.UserIdentity(auto_user=batchmodels.AutoUserSpecification(scope='task', elevation_level='admin'))
        )

    batch_service_client.task.add(job_id, task)

try:
    add_tasks(batch_client, _JOB_ID, 'test_task')
except batchmodels.BatchErrorException as err:
    print_batch_exception(err)
    raise

