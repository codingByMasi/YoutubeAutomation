# For Hugging Face Docker Spaces, Oracle Cloud VM, Render, Fly.io. Not tested in CI.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libcairo2 \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir boto3
RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH STUDIO_HOME=/data
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt streamlit
COPY --chown=user . .
EXPOSE 7860
CMD ["sh", "-c", "mkdir -p ${STUDIO_HOME} 2>/dev/null; streamlit run app.py --server.port=${PORT:-7860} --server.address=0.0.0.0"]
