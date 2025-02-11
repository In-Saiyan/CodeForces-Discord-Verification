FROM python:3.10
# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver (Explicit version)
ENV CHROMEDRIVER_VERSION=113.0.5672.63
RUN wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip -d /usr/local/bin/ \
    && rm chromedriver_linux64.zip

# Set environment variables to avoid sandbox issues
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_BIN=/usr/local/bin/chromedriver

WORKDIR /app

RUN mkdir /app/data

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
