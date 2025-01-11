FROM python:3.11
ENV APP_DIR=/apps/prepsom-backend
COPY . ${APP_DIR}
WORKDIR ${APP_DIR}
RUN pip3 install -r requirements.txt
RUN mkdir tmp_files
RUN chmod 777 *
CMD ["./start.sh"]