import os
import threading
import subprocess
import yt_dlp
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# ---------------- Helper Functions ----------------

def sanitize_filename(title):
    """
    Sanitizes the title to match yt-dlp's file naming conventions (basic replacement).
    """
    return "".join(c if c.isalnum() or c in " ._-()" else "_" for c in title)


def keep_only_largest_mp4(output_path, base_title, log_func=print):
    """
    Keeps the largest MP4 file associated with the given base title and removes all smaller MP4 duplicates.
    """
    mp4_files = [
        os.path.join(output_path, file)
        for file in os.listdir(output_path)
        if file.startswith(base_title) and file.endswith(".mp4")
    ]

    if mp4_files:
        largest_file = max(mp4_files, key=os.path.getsize)
        log_func
        for file in mp4_files:
            if file != largest_file:
                log_func(f"Removing smaller MP4 file: {file}")
                try:
                    os.remove(file)
                except Exception as e:
                    log_func(f"Error removing file {file}: {e}")

    def extract_audio_ffmpeg(video_path, mp3_path, audio_bitrate, log_func):
        """
        Uses FFmpeg to extract audio from the downloaded video.
        The video is assumed to have both video and audio.
        """
        # Build the command; here we re-encode audio using the specified bitrate.
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output if exists.
            "-i", video_path,
            "-vn",  # No video in output.
            "-ar", "44100",
            "-ac", "2",
            "-b:a", audio_bitrate,
            mp3_path
        ]
        log_func(f"Extracting MP3 via FFmpeg: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log_func(f"Audio extracted successfully: {mp3_path}")
        except subprocess.CalledProcessError as e:
            log_func(f"Error extracting audio: {e.stderr.decode()}")


def extract_audio_ffmpeg(video_file, mp3_file, audio_bitrate, log_func):
    pass


def start_download(url, video_format_id, download_mode, audio_bitrate, output_folder,
                   base_filename, log_func, progress_callback=None):
    """
    Downloads a video using the selected format.
    download_mode options:
      - "Video": Download merged video (with audio).
      - "MP3": Extract audio only (video removed).
      - "Both": Download merged video (with audio) then extract audio via FFmpeg.
    """
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    # Determine the output template.
    if base_filename:
        outtmpl = os.path.join(output_folder, base_filename + ".%(ext)s")
    else:
        outtmpl = os.path.join(output_folder, '%(title)s.%(ext)s')

    # Build format string.
    video_audio_format = f"{video_format_id}+bestaudio" if video_format_id else "best"

    ydl_opts = {
        'format': video_audio_format,
        'outtmpl': outtmpl,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'ignoreerrors': True,
    }

    # Configure yt_dlp options based on download_mode.
    if download_mode == "MP3":
        # Let FFmpegExtractAudio extract audio and remove the video.
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': audio_bitrate.rstrip('k'),
        }]
        ydl_opts['keepvideo'] = False
    elif download_mode == "Video":
        # Download video normally (merged with audio).
        pass
    elif download_mode == "Both":
        # Download video normally (merged with audio). Then, externally extract MP3.
        # Do not use a postprocessor so that the downloaded file remains unaltered.
        pass

    if progress_callback:
        ydl_opts['progress_hooks'] = [progress_callback]

    try:
        log_func(f"Starting download for: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if info is None:
            log_func("Skipped video (unavailable or error encountered).")
            return

        # Determine base title from info.
        base_title = sanitize_filename(info.get('title', base_filename or 'video'))
        log_func(f"Download finished. Base title: {base_title}")

        # For "Both" mode, run external FFmpeg to extract MP3.
        if download_mode == "Both":
            # Determine video filename.
            if base_filename:
                video_file = os.path.join(output_folder, base_filename + ".mp4")
                mp3_file = os.path.join(output_folder, base_filename + ".mp3")
            else:
                video_file = os.path.join(output_folder, sanitize_filename(info.get('title', 'video')) + ".mp4")
                mp3_file = os.path.join(output_folder, sanitize_filename(info.get('title', 'video')) + ".mp3")
            # Check if the video file exists.
            if os.path.exists(video_file):
                extract_audio_ffmpeg(video_file, mp3_file, audio_bitrate, log_func)
            else:
                log_func("Downloaded video file not found for audio extraction.")

        keep_only_largest_mp4(output_folder, base_title, log_func)
        log_func("Download completed successfully!")
    except Exception as e:
        log_func(f"An error occurred during download: {e}")


# ---------------- Playlist Row Widget ----------------

class PlaylistRow(tk.Frame):
    """
    A row representing a single video in a playlist.
    It shows:
      - A checkbox for selection.
      - The video title.
      - An OptionMenu for quality (initially "Not loaded").
      - A button to load quality options.
    """

    def __init__(self, master, entry, log_func):
        super().__init__(master, bd=1, relief="groove", padx=2, pady=2)
        self.entry = entry
        self.log = log_func
        self.selected = tk.BooleanVar(value=False)
        self.quality_options = []  # Holds available quality format dictionaries.
        self.quality_var = tk.StringVar(value="Not loaded")

        chk = tk.Checkbutton(self, variable=self.selected)
        chk.pack(side="left", padx=2)

        title = entry.get('title', 'No Title')
        lbl_title = tk.Label(self, text=title, wraplength=300, justify="left")
        lbl_title.pack(side="left", padx=2, fill="x", expand=True)

        self.quality_menu = tk.OptionMenu(self, self.quality_var, "Not loaded")
        self.quality_menu.config(width=30)
        self.quality_menu.pack(side="left", padx=2)

        btn = tk.Button(self, text="Load Quality", command=self.load_quality)
        btn.pack(side="left", padx=2)

    def load_quality(self):
        """Load all video formats (regardless of audio) for this video."""
        url = self.entry.get('webpage_url') or self.entry.get('url')
        if not url:
            self.log("No URL found for this video.")
            return
        threading.Thread(target=self._load_quality_thread, args=(url,), daemon=True).start()

    def _load_quality_thread(self, url):
        ydl_opts = {'skip_download': True, 'noplaylist': True, 'ignoreerrors': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info is None:
                self.log(f"Skipping unavailable video: {self.entry.get('title')}")
                return
            formats = []
            quality_list = []
            # List all formats that have a video codec.
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none':
                    resolution = fmt.get('resolution') or (f"{fmt.get('height')}p" if fmt.get('height') else "unknown")
                    desc = f"ID: {fmt.get('format_id')} | {fmt.get('ext')} | {resolution}"
                    if fmt.get('fps'):
                        desc += f" | {fmt.get('fps')}fps"
                    quality_list.append(desc)
                    formats.append(fmt)
            if quality_list:
                self.quality_options = formats
                self.quality_var.set(quality_list[0])
                self.quality_menu['menu'].delete(0, 'end')
                for choice in quality_list:
                    self.quality_menu['menu'].add_command(label=choice,
                                                          command=tk._setit(self.quality_var, choice))
                self.log(f"Loaded qualities for: {self.entry.get('title')}")
            else:
                self.log(f"No video formats found for: {self.entry.get('title')}")
        except Exception as e:
            self.log(f"Error loading qualities for {self.entry.get('title')}: {e}")


class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        # Update scrollregion when the inner frame changes size.
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # Create window inside canvas.
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


# ---------------- Single Video Frame ----------------

class SingleVideoFrame(tk.Frame):
    """
    Frame for single video mode. It displays:
      - The video title.
      - An OptionMenu for quality (initially "Not loaded").
      - A button to load quality options.
    """

    def __init__(self, master, info, log_func):
        super().__init__(master, bd=1, relief="groove", padx=5, pady=5)
        self.info = info
        self.log = log_func
        self.quality_options = []
        self.quality_var = tk.StringVar(value="Not loaded")

        title = info.get('title', 'No Title')
        lbl_title = tk.Label(self, text=title, wraplength=500, justify="left")
        lbl_title.pack(fill="x", padx=2, pady=2)

        quality_frame = tk.Frame(self)
        quality_frame.pack(fill="x", padx=2, pady=2)

        self.quality_menu = tk.OptionMenu(quality_frame, self.quality_var, "Not loaded")
        self.quality_menu.config(width=40)
        self.quality_menu.pack(side="left", padx=2)

        btn = tk.Button(quality_frame, text="Load Quality", command=self.load_quality)
        btn.pack(side="left", padx=2)

    def load_quality(self):
        # Use the URL from self.info.
        url = self.info.get('webpage_url') or self.info.get('url')
        if not url:
            messagebox.showerror("Error", "No video URL found!")
            return

        self.log(f"Extracting formats for: {url}")
        threading.Thread(target=self._load_formats_thread, args=(url,), daemon=True).start()

    def _load_formats_thread(self, url):
        ydl_opts = {'skip_download': True, 'noplaylist': True, 'ignoreerrors': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info is None:
                self.log("Skipping unavailable video.")
                return
            self.quality_options = []
            quality_list = []
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none':
                    resolution = fmt.get('resolution') or (f"{fmt.get('height')}p" if fmt.get('height') else "unknown")
                    desc = f"ID: {fmt.get('format_id')} | {fmt.get('ext')} | {resolution}"
                    if fmt.get('fps'):
                        desc += f" | {fmt.get('fps')}fps"
                    quality_list.append(desc)
                    self.quality_options.append(fmt)
            if not quality_list:
                self.log("No video formats found!")
                return
            # Update the OptionMenu in the main thread
            self.quality_var.set(quality_list[0])
            self.quality_menu['menu'].delete(0, 'end')
            for choice in quality_list:
                self.quality_menu['menu'].add_command(label=choice,
                                                      command=tk._setit(self.quality_var, choice))
            self.log("Video qualities loaded.")
        except Exception as e:
            self.log(f"Error loading formats: {e}")


# ---------------- Main GUI Application ----------------

class YTDLDownloaderGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.content_frame = None
        self.folder_label = None
        self.log_text = None
        self.single_video_frame = None
        self.progress_bar = None
        self.title("YT_DLP Downloader")
        self.geometry("850x800")
        self.resizable(True, True)

        # Global variables.
        self.url_var = tk.StringVar()
        self.audio_bitrate_var = tk.StringVar(value="320k")
        self.output_folder = ""
        self.base_filename_var = tk.StringVar()
        self.video_info = None  # For single video mode.
        self.mode = None  # 'single' or 'playlist'
        self.playlist_frame = None  # To store the playlist frame when loaded
        self.download_mode_var = tk.StringVar(value="Video")  # Options: Video, MP3, Both

        self.create_widgets()

    def create_widgets(self):
        pad_opts = {'padx': 5, 'pady': 5}

        # URL Input.
        url_frame = ttk.LabelFrame(self, text="Video or Playlist URL")
        url_frame.pack(fill="x", **pad_opts)
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=80)
        url_entry.pack(side="left", fill="x", expand=True, **pad_opts)
        load_button = ttk.Button(url_frame, text="Load", command=self.load_info)
        load_button.pack(side="left", **pad_opts)

        # Progress Bar.
        self.progress_bar = ttk.Progressbar(self, orient='horizontal', mode='determinate', maximum=100)
        self.progress_bar.pack(fill="x", padx=5, pady=5)

        # Content Frame: Will hold either a SingleVideoFrame or a PlaylistFrame.
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, **pad_opts)

        # Global Audio Options.
        audio_frame = ttk.LabelFrame(self, text="Audio Options")
        audio_frame.pack(fill="x", **pad_opts)
        ttk.Label(audio_frame, text="Audio Bitrate:").grid(row=0, column=0, sticky="e", **pad_opts)
        bitrate_options = ["320k", "256k", "192k", "128k"]
        bitrate_menu = ttk.OptionMenu(audio_frame, self.audio_bitrate_var, self.audio_bitrate_var.get(),
                                      *bitrate_options)
        bitrate_menu.grid(row=0, column=1, sticky="w", **pad_opts)

        # Download Type Options.
        mode_frame = ttk.LabelFrame(self, text="Download Type")
        mode_frame.pack(fill="x", **pad_opts)
        ttk.Label(mode_frame, text="Select Type:").grid(row=0, column=0, sticky="e", **pad_opts)
        mode_options = ["Video", "MP3", "Both"]
        mode_menu = ttk.OptionMenu(mode_frame, self.download_mode_var, self.download_mode_var.get(), *mode_options)
        mode_menu.grid(row=0, column=1, sticky="w", **pad_opts)

        # Output Options.
        output_frame = ttk.LabelFrame(self, text="Output Options")
        output_frame.pack(fill="x", **pad_opts)
        folder_button = ttk.Button(output_frame, text="Select Output Folder", command=self.select_output_folder)
        folder_button.grid(row=0, column=0, **pad_opts)
        self.folder_label = ttk.Label(output_frame, text="No folder selected")
        self.folder_label.grid(row=0, column=1, sticky="w", **pad_opts)
        ttk.Label(output_frame, text="Base Filename (optional):").grid(row=1, column=0, **pad_opts)
        filename_entry = ttk.Entry(output_frame, textvariable=self.base_filename_var, width=50)
        filename_entry.grid(row=1, column=1, sticky="w", **pad_opts)

        # Download Button.
        download_button = ttk.Button(self, text="Download", command=self.download)
        download_button.pack(pady=10)

        # Log Output.
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=True, **pad_opts)
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=12)
        self.log_text.pack(fill="both", expand=True, **pad_opts)

    def log(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder = folder
            self.folder_label.config(text=folder)
            self.log(f"Output folder selected: {folder}")

    def update_progress(self, percentage):
        self.progress_bar['value'] = percentage
        self.update_idletasks()

    def load_info(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL!")
            return

        # Clear previous content.
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.log(f"Extracting info from: {url}")
        threading.Thread(target=self._load_info_thread, args=(url,), daemon=True).start()

    def _load_info_thread(self, url):
        ydl_opts = {'skip_download': True, 'noplaylist': False, 'ignoreerrors': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info is None:
                self.log("Error extracting info or no valid videos found.")
                return
            if 'entries' in info:
                self.mode = 'playlist'
                entries = info['entries']
                self.log(f"Playlist detected with {len(entries)} videos.")
                # Create an options frame for playlist controls.
                options_frame = ttk.Frame(self.content_frame)
                options_frame.pack(fill="x", pady=5)
                # "Select All" checkbox.
                self.select_all_var = tk.BooleanVar()
                select_all_cb = ttk.Checkbutton(
                    options_frame,
                    text="Select All",
                    variable=self.select_all_var,
                    command=self.toggle_select_all
                )
                select_all_cb.pack(side="left", padx=5)
                # "Load Qualities for All" button.
                load_all_btn = ttk.Button(
                    options_frame,
                    text="Load Qualities for All",
                    command=self.load_all_qualities
                )
                load_all_btn.pack(side="left", padx=5)

                # Use the scrollable frame for the playlist rows.
                self.playlist_frame = ScrollableFrame(self.content_frame)
                self.playlist_frame.pack(fill="both", expand=True)
                self.after(0, lambda: self.show_playlist(entries))
            else:
                self.mode = 'single'
                self.video_info = info
                self.log("Single video detected.")
                self.after(0, lambda: self.show_single_video(info))
        except Exception as e:
            self.log(f"Error extracting info: {e}")

    def toggle_select_all(self):
        """Toggle the selection state of all playlist rows based on the checkbox."""
        select_all = self.select_all_var.get()
        if self.playlist_frame:
            for child in self.playlist_frame.scrollable_frame.winfo_children():
                if hasattr(child, 'selected'):
                    child.selected.set(select_all)

    def load_all_qualities(self):
        """Call the load_quality method for every playlist row."""
        if self.playlist_frame:
            for child in self.playlist_frame.scrollable_frame.winfo_children():
                if hasattr(child, 'load_quality'):
                    child.load_quality()

    def show_playlist(self, entries):
        for entry in entries:
            try:
                pr = PlaylistRow(self.playlist_frame.scrollable_frame, entry, self.log)
                pr.pack(fill="x", pady=2, padx=2)
            except Exception as e:
                self.log(f"Skipping an unavailable video: {e}")

    def show_single_video(self, info):
        self.single_video_frame = SingleVideoFrame(self.content_frame, info, self.log)
        self.single_video_frame.pack(fill="x", expand=True)

    def download(self):
        if not self.output_folder:
            messagebox.showerror("Error", "Please select an output folder!")
            return

        download_mode = self.download_mode_var.get()  # "Video", "MP3", or "Both"
        audio_bitrate = self.audio_bitrate_var.get()
        base_filename = self.base_filename_var.get().strip()

        if self.mode == 'single':
            url = self.video_info.get('webpage_url') or self.video_info.get('url')
            selected_quality = self.single_video_frame.quality_var.get()
            video_format_id = ""
            try:
                if "ID:" in selected_quality:
                    video_format_id = selected_quality.split("|")[0].split(":")[1].strip()
            except Exception as e:
                self.log(f"Error parsing quality: {e}")
            self.log("Starting download for single video...")

            def progress_hook(progress, self_ref=self):
                if progress.get('status') == 'downloading':
                    total = progress.get('total_bytes') or progress.get('total_bytes_estimate')
                    downloaded = progress.get('downloaded_bytes', 0)
                    if total:
                        percent = int(downloaded * 100 / total)
                        self_ref.after(0, lambda: self_ref.update_progress(percent))
                elif progress.get('status') in ('finished', 'error'):
                    self_ref.after(0, lambda: self_ref.update_progress(0))

            threading.Thread(target=start_download, args=(
                url,
                video_format_id,
                download_mode,
                audio_bitrate,
                self.output_folder,
                base_filename if base_filename else "",
                self.log,
                progress_hook,
            ), daemon=True).start()


        elif self.mode == 'playlist':

            selected_items = []

            if self.playlist_frame:

                for child in self.playlist_frame.scrollable_frame.winfo_children():

                    if hasattr(child, 'selected') and child.selected.get():
                        selected_items.append(child)

            if not selected_items:
                messagebox.showerror("Error", "No videos selected for download!")

                return

            # ... rest of your download logic for each selected video ...

            self.log(f"Starting download for {len(selected_items)} selected video(s)...")
            for idx, item in enumerate(selected_items, start=1):
                url = item.entry.get('webpage_url') or item.entry.get('url')
                selected_quality = item.quality_var.get()
                video_format_id = ""
                try:
                    if "ID:" in selected_quality:
                        video_format_id = selected_quality.split("|")[0].split(":")[1].strip()
                except Exception as e:
                    self.log(f"Error parsing quality for {item.entry.get('title')}: {e}")
                if base_filename:
                    video_base = f"{base_filename}_{sanitize_filename(item.entry.get('title', 'video'))}"
                else:
                    video_base = sanitize_filename(item.entry.get('title', f'video_{idx}'))

                def progress_hook(progress, self_ref=self):
                    if progress.get('status') == 'downloading':
                        total = progress.get('total_bytes') or progress.get('total_bytes_estimate')
                        downloaded = progress.get('downloaded_bytes', 0)
                        if total:
                            percent = int(downloaded * 100 / total)
                            self_ref.after(0, lambda: self_ref.update_progress(percent))
                    elif progress.get('status') in ('finished', 'error'):
                        self_ref.after(0, lambda: self_ref.update_progress(0))

                threading.Thread(target=start_download, args=(
                    url,
                    video_format_id,
                    download_mode,
                    audio_bitrate,
                    self.output_folder,
                    video_base,
                    self.log,
                    progress_hook,
                ), daemon=True).start()

        else:
            messagebox.showerror("Error", "No video information loaded!")


# ---------------- Main ----------------

if __name__ == "__main__":
    app = YTDLDownloaderGui()
    app.mainloop()
