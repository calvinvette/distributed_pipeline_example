Building off of the ~/workspace/drone-image-ml project, Generate a generic multi stage pipeline project that would support this drone ML image ingestion model that they are doing.

Each stage of the pipeline should be supported by its own container that will be registered into ECR after it is built via GitHub actions. We will support UV and left hook, commit actions as we have in the previous projects. Make sure we include the nbstrip out to handle notebook, stripping, as well as carriage return light feed adjustments, and extra carriage. Return line feed at the end of the files to prevent any kind of consumption issue.

The first stage containers should be trigger on a new file upload to an S3 bucket or to do a scheduled watch and to consume all images that were not previously consumed. This stage will do the albumentations and store them in a specified output bucket for the next stage, Linking the annotation manifest and image files as described in the manifest project we created earlier. 

The second stage container will listen for a trigger or do a scheduled watch and perform image normalization, specifically sizing which can be configured via environment, variable or command line parameter; number of instances, instance type, manifest store registry (also using the manifest project we created earlier).  The output will be to a configurable S3 bucket, which will be training data for the next stage.

The third stage container will be scheduled only and will focus on training. We will assume a training run begins at 9pm US Eastern Time and runs daily. The script to run the training job will take a number of instances, instance type, MLFlow Tracking Server, MLFlow Model Registry (assume they may be different), manifest store registry (using the manifest project we created earlier). 

The fourth stage container will be an inference container. It will be able to consume new images without annotations and use the trained model to create the annotations. The format will be compatible with the input format for the first stage pipeline, however we will output to a different S3 bucket for potential HITL modification and retraining or for final output. Containers, number of instances, instance type, listening bucket, output bucket, MLFlow Tracing server will all be configurable. Create an optional K8S pod manifest for easy scaling; assume EKS if necessary but try to be generic.  Include performance gathering via Prometheus and Grafana (with configurable server entries).

Create Terraform files for all stages.

Create Unit tests for each stage except training. Include test scripts to verify deployment. 

Assume AWS keys and other generic identity information or URLs will be supplied via .env file or secrets. Provide an example of each file with documentation of what to supply and where to get the information.

Create a verbose README.md that describes all of the stages.

Create a verbose per-stage README.md that describes how to launch, verify, monitor the stage.

Create verbose instructions to describe how to implement the testing. 

Create a setup script that can query the user to populate environment files as necessary.
