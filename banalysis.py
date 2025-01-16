import yt_dlp

def download_bilibili_video(bv_id, output_path):
    url = f"https://www.bilibili.com/video/{bv_id}"
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo+bestaudio/best',  # 下载最佳视频和音频
        'merge_output_format': 'mp4',  # 合并为mp4格式
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
