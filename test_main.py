import unittest
import argparse
from unittest.mock import patch, MagicMock, call

# Since the script is not a package, we need to import it this way
# This assumes test_main.py is in the same directory as main.py
import main

class TestFrameExtractor(unittest.TestCase):

    # --------------------------------------------------------------------------- #
    # Test Utilidades
    # --------------------------------------------------------------------------- #

    def test_validate_time_valid(self):
        """Tests that validate_time accepts various correct time formats."""
        valid_times = ['90', '01:30', '00:01:30', '90.5', '01:30.123', '12:34:56']
        for t in valid_times:
            with self.subTest(time=t):
                self.assertEqual(main.validate_time(t), t)

    def test_validate_time_invalid(self):
        """Tests that validate_time raises an error for invalid formats."""
        invalid_times = ['abc', '1:2:3:4', '1:60', '12:34:56:78']
        for t in invalid_times:
            with self.subTest(time=t):
                with self.assertRaises(argparse.ArgumentTypeError):
                    main.validate_time(t)

    def test_validate_time_none(self):
        """Tests that validate_time correctly handles None input."""
        self.assertIsNone(main.validate_time(None))

    def test_sanitize_filename(self):
        """Tests the sanitization of filenames."""
        self.assertEqual(main.sanitize_filename('title with *?'), 'title with __')
        self.assertEqual(main.sanitize_filename('<>/\\|:"*?'), '_________')
        self.assertEqual(main.sanitize_filename('  leading and trailing spaces  '), 'leading and trailing spaces')
        self.assertEqual(main.sanitize_filename(''), 'video')
        self.assertEqual(main.sanitize_filename('   '), 'video')

    @patch('main.shutil.which')
    @patch('main.sys.exit')
    @patch('builtins.print')
    def test_check_dependency_found(self, mock_print, mock_exit, mock_which):
        """Tests check_dependency when the command is found."""
        mock_which.return_value = '/usr/bin/ffmpeg'
        main.check_dependency('ffmpeg', 'Install it.')
        mock_exit.assert_not_called()
        mock_print.assert_not_called()

    @patch('main.shutil.which')
    @patch('main.sys.exit')
    @patch('builtins.print')
    def test_check_dependency_not_found(self, mock_print, mock_exit, mock_which):
        """Tests check_dependency when the command is NOT found."""
        mock_which.return_value = None
        main.check_dependency('nonexistent', 'Install it.')
        mock_print.assert_called_with("❌ No se encontró 'nonexistent' en el sistema. Install it.")
        mock_exit.assert_called_once_with(1)

    # --------------------------------------------------------------------------- #
    # Test yt-dlp wrappers
    # --------------------------------------------------------------------------- #

    @patch('main.subprocess.run')
    def test_get_video_title_success(self, mock_run):
        """Tests getting a video title successfully."""
        mock_process = MagicMock()
        mock_process.stdout = "  My Video Title *?  \n"
        mock_run.return_value = mock_process

        title = main.get_video_title("some_url")
        self.assertEqual(title, "My Video Title __")
        mock_run.assert_called_once()

    @patch('main.subprocess.run')
    def test_get_video_title_failure(self, mock_run):
        """Tests the fallback title when yt-dlp fails."""
        mock_run.side_effect = Exception("yt-dlp failed")
        title = main.get_video_title("some_url")
        self.assertEqual(title, "video")

    @patch('main.subprocess.run')
    def test_get_direct_stream_url_success(self, mock_run):
        """Tests getting a stream URL successfully."""
        mock_process = MagicMock()
        mock_process.stdout = "http://direct.url/video.mp4\n"
        mock_run.return_value = mock_process

        url = main.get_direct_stream_url("some_url", "best")
        self.assertEqual(url, "http://direct.url/video.mp4")

    @patch('main.subprocess.run')
    def test_get_direct_stream_url_with_cookies(self, mock_run):
        """Tests that the cookies parameter is correctly passed to yt-dlp."""
        mock_process = MagicMock()
        mock_process.stdout = "http://direct.url/video.mp4\n"
        mock_run.return_value = mock_process

        main.get_direct_stream_url("some_url", "best", cookies_file="/path/to/cookies.txt")
        
        # Check that '--cookies' and the path were in the command arguments
        args, kwargs = mock_run.call_args
        self.assertIn("--cookies", args[0])
        self.assertIn("/path/to/cookies.txt", args[0])

    @patch('main.sys.exit')
    @patch('builtins.print')
    @patch('main.subprocess.run')
    def test_get_direct_stream_url_no_url_returned(self, mock_run, mock_print, mock_exit):
        """Tests when yt-dlp returns an empty stdout."""
        mock_process = MagicMock()
        mock_process.stdout = " \n " # Empty or whitespace
        mock_run.return_value = mock_process

        main.get_direct_stream_url("some_url", "best")
        mock_print.assert_called_with("❌ yt-dlp no devolvió ninguna URL de stream. "
              "¿El video es privado, geo-restringido o requiere login?")
        mock_exit.assert_called_once_with(1)

    # --------------------------------------------------------------------------- #
    # Test ffmpeg wrappers
    # --------------------------------------------------------------------------- #

    def test_build_ffmpeg_cmd_basic(self):
        """Tests the basic ffmpeg command build."""
        cmd = main.build_ffmpeg_cmd("http://url", "/out", None, None, None, "jpg", 2)
        expected = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-stats",
            "-i", "http://url",
            "-q:v", "2",
            "/out/frame_%05d.jpg"
        ]
        self.assertEqual(cmd, expected)

    def test_build_ffmpeg_cmd_full(self):
        """Tests the ffmpeg command build with all options."""
        cmd = main.build_ffmpeg_cmd("http://url", "/out", "00:01:00", "00:02:00", 10, "png", 2)
        expected = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-stats",
            "-ss", "00:01:00",
            "-i", "http://url",
            "-to", "00:02:00",
            "-vf", "fps=10",
            "/out/frame_%05d.png"
        ]
        self.assertEqual(cmd, expected)

    def test_build_ffmpeg_cmd_no_quality_for_png(self):
        """Tests that '-q:v' is not added for png format."""
        cmd = main.build_ffmpeg_cmd("http://url", "/out", None, None, None, "png", 2)
        self.assertNotIn("-q:v", cmd)

    @patch('main.os.path.isdir', return_value=True)
    @patch('main.os.listdir')
    def test_count_frames(self, mock_listdir, mock_isdir):
        """Tests counting extracted frames in a directory."""
        mock_listdir.return_value = ['frame_001.jpg', 'frame_002.jpg', 'other.txt']
        count = main.count_frames('/fake/dir', 'jpg')
        self.assertEqual(count, 2)
        mock_isdir.assert_called_once_with('/fake/dir')
        mock_listdir.assert_called_once_with('/fake/dir')

    @patch('main.os.path.isdir', return_value=False)
    def test_count_frames_no_dir(self, mock_isdir):
        """Tests counting frames when the directory doesn't exist."""
        count = main.count_frames('/nonexistent/dir', 'jpg')
        self.assertEqual(count, 0)
        mock_isdir.assert_called_once_with('/nonexistent/dir')

    # --------------------------------------------------------------------------- #
    # Test Main function
    # --------------------------------------------------------------------------- #

    @patch('main.sys.argv', ['main.py', 'http://test.url', '--output', '/tmp/test', '--fps', '1'])
    @patch('main.check_dependency')
    @patch('main.get_video_title', return_value='test_video')
    @patch('main.os.makedirs')
    @patch('main.get_direct_stream_url', return_value='http://direct.url')
    @patch('main.build_ffmpeg_cmd', return_value=['ffmpeg', '...'])
    @patch('main.run_ffmpeg')
    @patch('main.count_frames', return_value=10)
    @patch('builtins.print')
    def test_main_flow(self, mock_print, mock_count, mock_run_ffmpeg, mock_build, mock_get_stream, mock_makedirs, mock_get_title, mock_check_dep):
        """Tests the main execution flow with mocks."""
        main.main()

        # Check dependencies were checked
        mock_check_dep.assert_has_calls([call('yt-dlp', 'Instálalo con: pip install -U yt-dlp'), call('ffmpeg', 'Instálalo desde https://ffmpeg.org/download.html')])

        # Check functions were called with correct arguments
        mock_get_title.assert_called_once_with('http://test.url')
        mock_makedirs.assert_called_once_with('/tmp/test', exist_ok=True)
        mock_get_stream.assert_called_once()
        mock_build.assert_called_once()
        mock_run_ffmpeg.assert_called_once_with(['ffmpeg', '...'])
        mock_count.assert_called_once_with('/tmp/test', 'jpg')

        # Check final success message
        # We check the last call to print
        final_print_call = mock_print.call_args_list[-1]
        self.assertIn("📂 Carpeta: /tmp/test", str(final_print_call))


if __name__ == '__main__':
    unittest.main()