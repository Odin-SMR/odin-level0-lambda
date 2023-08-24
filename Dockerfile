FROM public.ecr.aws/lambda/python:3.10

# Install prerequisite psql requirements
RUN yum makecache fast
RUN yum update -y
RUN yum groupinstall 'Development Tools' -y
RUN yum install postgresql-devel -y

# Install the function's dependencies using file requirements.txt
# from your project folder.

COPY ./level0/requirements.txt  .
RUN  pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY ./level0/handlers/*.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "handler.handler" ] 
