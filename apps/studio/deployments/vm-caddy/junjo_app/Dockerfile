# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set Python to run in unbuffered mode to ensure logs stream in real-time
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file into the container at /usr/src/app
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .

# Run main.py when the container launches
CMD ["python", "./main.py"]