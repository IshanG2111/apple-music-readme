import os
import random
from base64 import b64encode

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template

from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")), autoescape=False
)

load_dotenv()


class RenderCard:
    def __init__(self) -> None:
        self.__data = {}

    def _get_credentials(self):
        load_dotenv(override=True)
        token = os.getenv("AUTH_TOKEN") or os.getenv("AUTHORIZATION") or os.getenv("TOKEN")
        cookie = os.getenv("COOKIE") or os.getenv("Cookie")
        media_user_token = (
            os.getenv("MEDIA_USER_TOKEN")
            or os.getenv("media-user-token")
            or os.getenv("MEDIA_TOKEN")
        )

        if token:
            token = token.strip().strip("'\"")
            if token.startswith("Bearer "):
                token = token.replace("Bearer ", "", 1).strip()
        if cookie:
            cookie = cookie.strip().strip("'\"")
        if media_user_token:
            media_user_token = media_user_token.strip().strip("'\"")

        return token, cookie, media_user_token

    def __apple_music_icon_b64(self) -> str:
        """
        Returns Base64 encoded Apple Music icon.
        """
        icon_path = os.path.join(BASE_DIR, "static", "icon.png")
        if os.path.exists(icon_path):
            with open(icon_path, "rb") as f:
                return b64encode(f.read()).decode("ascii")
        return ""

    def __album_art_b64(self, img_url: str) -> str:
        """Converts album art to base64

        Args:
            img_url (str): CDN URL of the album_art
        """
        if not img_url:
            return ""
        try:
            res = requests.get(img_url, headers={}, cookies={}, timeout=10)
            if res.status_code == 200:
                return b64encode(res.content).decode("ascii")
        except Exception as e:
            print(f"Error fetching album art: {e}")
        return ""

    def __fetch_recently_played_tracks(self, token, cookie, media_user_token):
        """
        Fetches the actual recently played tracks from Apple Music playback history.
        """
        url = "https://amp-api.music.apple.com/v1/me/recent/played/tracks?limit=10"
        headers = {
            "Authorization": f"Bearer {token}",
            "Cookie": cookie,
            "media-user-token": media_user_token,
            "origin": "https://music.apple.com",
            "referer": "https://music.apple.com/",
        }

        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                tracks = data.get("data", [])
                if tracks:
                    # Most recently played track is the first item!
                    track = tracks[0]
                    attrs = track.get("attributes", {})
                    name = attrs.get("name", "Unknown Track")
                    artist_name = attrs.get("artistName", "Unknown Artist")
                    artwork = attrs.get("artwork", {})
                    image_url = artwork.get("url", "")
                    if image_url:
                        image_url = (
                            image_url.replace("{w}", "632")
                            .replace("{h}", "632")
                            .replace("{f}", "jpg")
                        )
                    return {
                        "name": name,
                        "artist_name": artist_name,
                        "image_url": image_url,
                        "status_text": "RECENTLY PLAYED",
                    }
        except Exception as e:
            print(f"Exception fetching recently played tracks: {e}")
        return None

    def __fetch_music_data(self):
        """
        Fetches current/recently played song, falling back to recently added library albums.
        """
        token, cookie, media_user_token = self._get_credentials()

        if not token or not cookie or not media_user_token:
            missing = []
            if not token:
                missing.append("AUTH_TOKEN")
            if not cookie:
                missing.append("COOKIE")
            if not media_user_token:
                missing.append("MEDIA_USER_TOKEN")
            self.__data = {
                "name": "Missing Credentials",
                "artist_name": f"Set {', '.join(missing)} in Vercel",
                "image_url": "",
                "status_text": "ERROR",
            }
            return

        # 1. Primary: Try actual recently played tracks
        recent_track = self.__fetch_recently_played_tracks(token, cookie, media_user_token)
        if recent_track:
            self.__data = recent_track
            return

        # 2. Fallback: Recently added library albums
        url = "https://amp-api.music.apple.com/v1/me/library/recently-added?art%5Burl%5D=f&fields%5Balbums%5D=artistName%2CartistUrl%2Cartwork%2CcontentRating%2CeditorialArtwork%2Cname%2CplayParams%2CreleaseDate%2Curl&fields%5Bartists%5D=name%2Curl&format%5Bresources%5D=map&includeOnly=catalog%2Cartists&include%5Blibrary-albums%5D=artists&include%5Blibrary-artists%5D=catalog&limit=25&omit%5Bresource%5D=autos"
        headers = {
            "Authorization": f"Bearer {token}",
            "Cookie": cookie,
            "media-user-token": media_user_token,
            "origin": "https://music.apple.com",
            "referer": "https://music.apple.com/",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Apple Music API error: {response.status_code}")
                msg = "Tokens Expired or Invalid" if response.status_code in (401, 403) else f"HTTP {response.status_code}"
                self.__data = {
                    "name": "Apple Music Error",
                    "artist_name": msg,
                    "image_url": "",
                    "status_text": "ERROR",
                }
                return

            try:
                data = response.json()
            except Exception:
                self.__data = {
                    "name": "API Response Error",
                    "artist_name": "Invalid response format",
                    "image_url": "",
                    "status_text": "ERROR",
                }
                return

            resources = data.get("resources", {})
            library_albums = resources.get("library-albums", {})
            albums = list(library_albums.values())

            if not albums:
                self.__data = {
                    "name": "No Albums Found",
                    "artist_name": "Apple Music Library",
                    "image_url": "",
                    "status_text": "LIBRARY",
                }
                return

            album_data = []
            for album in albums:
                attrs = album.get("attributes", {})
                artwork = attrs.get("artwork", {})
                image_url = artwork.get("url", "")

                if not image_url:
                    continue

                image_url = (
                    image_url.replace("{w}", "632")
                    .replace("{h}", "632")
                    .replace("{f}", "jpg")
                )
                name = attrs.get("name", "Unknown")
                artist_name = attrs.get("artistName", "Unknown")

                album_data.append({
                    "name": name,
                    "artist_name": artist_name,
                    "image_url": image_url,
                    "status_text": "RECENTLY ADDED",
                })

            if album_data:
                self.__data = album_data[0]
            else:
                self.__data = {
                    "name": "No Artwork Found",
                    "artist_name": "Apple Music Library",
                    "image_url": "",
                    "status_text": "LIBRARY",
                }
        except Exception as e:
            print(f"Exception while fetching: {e}")
            self.__data = {
                "name": "Apple Music Error",
                "artist_name": str(e)[:30],
                "image_url": "",
                "status_text": "ERROR",
            }

    def generate_card(self) -> str:
        """Generates the SVG card

        Returns:
            str: SVG card
        """
        self.__fetch_music_data()
        image = self.__album_art_b64(self.__data.get("image_url", ""))
        album_name = self.__data.get("name", "Unknown")
        album_name = album_name.replace("&", "and")
        artist_name = self.__data.get("artist_name", "")
        artist_name = artist_name.replace("&", "and")
        album_name = (
            (album_name[:24] + "...") if len(album_name) > 26 else album_name
        )
        status_text = self.__data.get("status_text", "RECENTLY PLAYED")
        icon = self.__apple_music_icon_b64()

        template = jinja_env.get_template("card.html.j2")
        svg = template.render(
            album_art=image,
            album_name=album_name,
            artist_name=artist_name,
            apple_icon=icon,
            status_text=status_text,
        )

        return svg


app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
rc = RenderCard()


@app.route("/debug")
def debug():
    token, cookie, media_user_token = rc._get_credentials()
    status = {
        "AUTH_TOKEN_configured": bool(token),
        "AUTH_TOKEN_length": len(token) if token else 0,
        "COOKIE_configured": bool(cookie),
        "COOKIE_length": len(cookie) if cookie else 0,
        "MEDIA_USER_TOKEN_configured": bool(media_user_token),
        "MEDIA_USER_TOKEN_length": len(media_user_token) if media_user_token else 0,
    }

    if token and cookie and media_user_token:
        # Check primary endpoint: recent played tracks
        headers = {
            "Authorization": f"Bearer {token}",
            "Cookie": cookie,
            "media-user-token": media_user_token,
            "origin": "https://music.apple.com",
            "referer": "https://music.apple.com/",
        }
        try:
            res = requests.get(
                "https://amp-api.music.apple.com/v1/me/recent/played/tracks?limit=1",
                headers=headers,
                timeout=5,
            )
            status["apple_recent_played_status"] = res.status_code
            if res.status_code == 200:
                data = res.json().get("data", [])
                if data:
                    track_attrs = data[0].get("attributes", {})
                    status["most_recent_song"] = track_attrs.get("name")
                    status["most_recent_artist"] = track_attrs.get("artistName")
            else:
                status["apple_recent_played_error"] = res.text[:150]
        except Exception as e:
            status["apple_recent_played_exception"] = str(e)

    return jsonify(status)


@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>")
def handle_all(path):
    svg = rc.generate_card()
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "s-maxage=1, no-cache, no-store, must-revalidate"
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5050)
