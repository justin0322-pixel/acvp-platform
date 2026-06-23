FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" pydantic pydantic-settings pyjwt arq
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
