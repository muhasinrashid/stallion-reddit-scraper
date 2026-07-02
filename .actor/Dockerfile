FROM apify/actor-python-playwright:3.13

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install-deps chromium \
    && playwright install chromium

COPY . ./

CMD ["python", "-m", "src"]
