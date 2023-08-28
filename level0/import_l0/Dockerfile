FROM public.ecr.aws/lambda/python:3.10

# Install prerequisite psql requirements
RUN yum makecache fast
RUN yum update -y
RUN yum groupinstall 'Development Tools' -y
RUN yum install postgresql-devel -y

# Install the function's dependencies using file requirements.txt
# from your project folder.

COPY ./requirements.txt  .
RUN  pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "handler.import_l0_handler.import_l0_handler" ] 
