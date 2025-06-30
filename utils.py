import base64
import streamlit as st
import boto3
import json
import pandas as pd
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

load_dotenv()

aws_key = os.getenv("AWS_ACCESS_KEY_ID")

# AWS Secrets (for production use)
def get_secret(secret_name: str, region_name: str = "ap-south-1") -> dict:
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)

        if "SecretString" in response:
            return json.loads(response["SecretString"])
        else:
            return json.loads(base64.b64decode(response["SecretBinary"]).decode("utf-8"))
    except Exception as e:
        st.error(f"❌ Failed to load secret: {e}")
        return {}

# DynamoDB connection
@st.cache_resource
def init_dynamodb():
    """Handles AWS credentials for both local and cloud environments"""
    try:
        # Configuration for local development
        local_config = {
            'region_name': 'ap-south-1'
        }
        
        # Try Streamlit secrets first (for cloud deployment)
        if hasattr(st, 'secrets') and 'aws' in st.secrets:
            local_config.update({
                'aws_access_key_id': st.secrets["aws"]["AWS_ACCESS_KEY_ID"],
                'aws_secret_access_key': st.secrets["aws"]["AWS_SECRET_ACCESS_KEY"]
            })
        else:
            # Fallback to environment variables (for local development)
            from dotenv import load_dotenv
            load_dotenv()
            
            local_config.update({
                'aws_access_key_id': os.getenv("AWS_ACCESS_KEY_ID"),
                'aws_secret_access_key': os.getenv("AWS_SECRET_ACCESS_KEY")
            })

        return boto3.resource('dynamodb', **local_config)
        
    except Exception as e:
        st.error(f"❌ AWS Configuration Error: {str(e)}")
        return None
    
# platform detection from domain
def get_platform_from_url(url):
    try:
        domain = urlparse(url.lower()).netloc.replace('www.', '')

        platform_map = {
            'linkedin.com': 'LinkedIn',
            'x.com': 'X (Twitter)',
            'twitter.com': 'X (Twitter)',
            'github.com': 'GitHub',
            'medium.com': 'Medium',
            'arxiv.org': 'arXiv',
            'hai.stanford.edu': 'HAI Stanford',
            'nextgenai.simppl.org': 'NextGenAI',
            'youtube.com': 'YouTube',
            'substack.com': 'Substack'
        }

        # Try exact match first
        if domain in platform_map:
            return platform_map[domain]

        # Fallback to root domain
        return domain.split('.')[0].title()
    except:
        return 'Unknown'

# Topic extractor via page title / OpenGraph
@st.cache_data(show_spinner=False)
def extract_title_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=5, headers=headers)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Try OpenGraph <meta property="og:title">
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()

        # Try <title> tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # Try H1 tag
        h1 = soup.find('h1')
        if h1:
            return h1.text.strip()

        return 'Unclassified'
    except:
        return 'Unclassified'
