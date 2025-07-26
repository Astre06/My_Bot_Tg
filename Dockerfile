# Use official Python 3.11 image
FROM python:3.11

# Set work directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Run the bot
CMD ["python", "bot.py"]
