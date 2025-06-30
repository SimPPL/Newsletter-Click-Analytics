from urllib.parse import urlparse
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime as dt, timedelta
from boto3.dynamodb.conditions import Attr
from utils import (
    init_dynamodb,
    get_platform_from_url,
    extract_title_from_url
)

# Constants
PLATFORM_MAPPING = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'linkedin.com': 'LinkedIn',
    'twitter.com': 'Twitter',
    'x.com': 'Twitter',
    'facebook.com': 'Facebook',
    'instagram.com': 'Instagram',
    'github.com': 'GitHub',
    'medium.com': 'Medium',
    'substack.com': 'Substack',
}

SECTION_MAPPING = {
    "highlights": "Highlights of the Month",
    "whats-cooking": "What's Cooking at SimPPL",
    "what-we-are-reading": "What We Are Reading at SimPPL",
}

@st.cache_data(ttl=300)
def fetch_click_events(start_date, end_date):
    """Fetch click events from DynamoDB"""
    dynamodb = init_dynamodb()
    if not dynamodb:
        return pd.DataFrame()

    try:
        table = dynamodb.Table('ClickEvents')
        start_str = start_date.strftime("%Y-%m-%dT00:00:00")
        end_str = end_date.strftime("%Y-%m-%dT23:59:59")

        response = table.scan(
            FilterExpression=Attr('timestamp').between(start_str, end_str)
        )
        items = response.get('Items', [])

        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('timestamp').between(start_str, end_str),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        return pd.DataFrame(items)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def detect_section(url):
    """Categorize URLs into newsletter sections"""
    if not url:
        return "Other Links"
    
    url_lower = url.lower()
    
    # Social/footer links
    social_patterns = [
        "twitter.com/simppl", 
        "linkedin.com/company/simppl",
        "github.com/simppl",
        "facebook.com/simppl",
        "instagram.com/simppl",
        "simppl.org",
        "/contact", "/about", "/subscribe"
    ]
    if any(pattern in url_lower for pattern in social_patterns):
        return "Social Links"
    
    # Newsletter sections
    for keyword, section in SECTION_MAPPING.items():
        if keyword in url_lower:
            return section
            
    return "Other Links"

def create_analytics_dashboard():
    """Main Streamlit dashboard layout"""
    st.title("📊 SimPPL Newsletter Analytics Dashboard")

    # Date selection
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=dt.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", value=dt.now().date())

    if start_date > end_date:
        st.error("Start date must be before end date")
        return

    # Load data
    with st.spinner("Loading click events..."):
        df = fetch_click_events(start_date, end_date)

    if df.empty:
        st.warning("No click events found for the selected date range.")
        return

    # Process data
    df = df[~df['original_url'].str.contains("simppl-newsletter-bucket", na=False)]
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    df['hour'] = df['timestamp'].dt.hour
    df['platform'] = df['original_url'].apply(get_platform_from_url)
    df['topic_title'] = df['original_url'].apply(extract_title_from_url)
    df['section'] = df['original_url'].apply(detect_section)

    # Key Metrics
    st.subheader("📈 Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Clicks", len(df))
    with col2: st.metric("Unique Links", df['link_id'].nunique())
    with col3: st.metric("Unique Recipients", df['recipient_email'].nunique())
    with col4: st.metric("Avg Clicks/Day", f"{(len(df) / max(1, (end_date - start_date).days + 1)):.1f}")

    # Top Articles by Title
    st.subheader("📰 Top Clicked Articles by Title")
    title_counts = df['topic_title'].value_counts().head(15)
    fig_titles = px.bar(
        x=title_counts.values,
        y=title_counts.index,
        orientation='h',
        title="Most Engaging Articles",
        labels={'x': 'Clicks', 'y': 'Title'},
        color=title_counts.values
    )
    st.plotly_chart(fig_titles, use_container_width=True)

    # Platform Breakdown
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🌐 Platform Breakdown")
        platform_counts = df['platform'].value_counts()
        fig_platform = px.bar(
            x=platform_counts.values,
            y=platform_counts.index,
            orientation='h',
            title="Top Platforms",
            color=platform_counts.values
        )
        st.plotly_chart(fig_platform, use_container_width=True)

    with col2:
        st.subheader("📆 Daily Clicks")
        daily = df.groupby('date').size().reset_index(name='clicks')
        st.plotly_chart(px.line(daily, x='date', y='clicks', title="Clicks Over Time", markers=True), use_container_width=True)

    # Time-based
    st.subheader("⏰ Hourly Activity")
    hourly = df.groupby('hour').size().reset_index(name='clicks')
    st.plotly_chart(px.bar(hourly, x='hour', y='clicks', title="Clicks by Hour", color='clicks'), use_container_width=True)

    # Detailed Tabs
    st.subheader("📋 Detailed Views")
    tab1, tab2 = st.tabs(["Top Links", "Platform Summary"])

    with tab1:
        top_links = df.groupby(['topic_title', 'original_url', 'platform']).size().reset_index(name='clicks')
        top_links = top_links.sort_values('clicks', ascending=False).head(20)
        st.dataframe(top_links, use_container_width=True)

    with tab2:
        platform_summary = df.groupby(['platform']).agg({
            'click_id': 'count',
            'recipient_email': 'nunique',
            'link_id': 'nunique'
        }).rename(columns={
            'click_id': 'Total Clicks',
            'recipient_email': 'Unique Recipients',
            'link_id': 'Unique Links'
        }).sort_values('Total Clicks', ascending=False)
        st.dataframe(platform_summary, use_container_width=True)

    # Export
    st.subheader("📥 Export Options")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Download Raw CSV"):
            export_df = df[['timestamp', 'platform', 'original_url', 'topic_title', 'recipient_email', 'link_id']]
            csv = export_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"simppl_clicks_{start_date}_{end_date}.csv",
                mime="text/csv"
            )

    with col2:
        if st.button("Download Summary Report"):
            summary = {
                'Top Articles': df['topic_title'].value_counts().to_dict(),
                'Top Platforms': df['platform'].value_counts().to_dict(),
                'Daily Summary': df.groupby('date').size().to_dict()
            }
            summary_df = pd.DataFrame(list(summary.items()), columns=["Metric", "Data"])
            st.download_button("Download Summary CSV", summary_df.to_csv(index=False), f"summary_{start_date}_{end_date}.csv", mime="text/csv")

if __name__ == "__main__":
    create_analytics_dashboard()