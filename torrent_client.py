import hashlib
import bencodepy

class Torrent:
    """
    Represents the data stored in a .torrent file.
    """
    def __init__(self, filename):
        """
        Initializes a Torrent object from a .torrent file.

        Args:
            filename (str): The path to the .torrent file.
        """
        self.filename = filename
        self.metadata = self._load_from_file(filename)
        self.info_hash = self._calculate_info_hash()
        self.announce_list = self._get_announce_list()
        self.file_info = self._get_file_info()

    def _load_from_file(self, filename):
        """
        Loads and decodes the .torrent file.

        Args:
            filename (str): The path to the .torrent file.

        Returns:
            dict: The decoded torrent metadata.
        """
        try:
            with open(filename, 'rb') as f:
                # bencodepy is a robust library for bencoding,
                # which is simpler than writing a parser from scratch for this tutorial.
                return bencodepy.decode(f.read())
        except FileNotFoundError:
            print(f"Error: File not found at {filename}")
            exit()
        except Exception as e:
            print(f"Error decoding torrent file: {e}")
            exit()

    def _calculate_info_hash(self):
        """
        Calculates the SHA1 hash of the 'info' dictionary from the torrent metadata.
        This hash is used to identify the torrent with the tracker and peers.

        Returns:
            bytes: The 20-byte SHA1 hash.
        """
        info_dict = self.metadata.get(b'info', {})
        # The info dictionary must be bencoded before hashing
        encoded_info = bencodepy.encode(info_dict)
        return hashlib.sha1(encoded_info).digest()

    def _get_announce_list(self):
        """
        Extracts the list of tracker URLs from the metadata.
        Trackers are servers that help peers find each other.

        Returns:
            list: A list of tracker URLs (strings).
        """
        if b'announce-list' in self.metadata:
            # The announce-list is a list of lists of strings
            trackers = []
            for tier in self.metadata[b'announce-list']:
                for tracker in tier:
                    trackers.append(tracker.decode('utf-8'))
            return trackers
        elif b'announce' in self.metadata:
            # Fallback to the single 'announce' key
            return [self.metadata[b'announce'].decode('utf-8')]
        else:
            return []

    def _get_file_info(self):
        """
        Extracts information about the file(s) to be downloaded.
        This can be a single file or multiple files within a directory.

        Returns:
            dict: A dictionary containing file information.
        """
        info = self.metadata.get(b'info', {})
        file_info = {}

        if b'name' in info:
            file_info['name'] = info[b'name'].decode('utf-8')

        if b'length' in info:
            # Single file mode
            file_info['type'] = 'single'
            file_info['length'] = info[b'length']
            file_info['files'] = [{'path': [info[b'name']], 'length': info[b'length']}]
        elif b'files' in info:
            # Multiple file mode
            file_info['type'] = 'multiple'
            files = []
            total_size = 0
            for file_dict in info[b'files']:
                path_parts = [p.decode('utf-8') for p in file_dict[b'path']]
                length = file_dict[b'length']
                files.append({'path': path_parts, 'length': length})
                total_size += length
            file_info['files'] = files
            file_info['length'] = total_size

        if b'piece length' in info:
            file_info['piece_length'] = info[b'piece length']

        if b'pieces' in info:
            # The 'pieces' string is a concatenation of 20-byte SHA1 hashes
            # of each piece. We split it into a list of these hashes.
            pieces_raw = info[b'pieces']
            file_info['pieces'] = [pieces_raw[i:i+20] for i in range(0, len(pieces_raw), 20)]

        return file_info

    def __str__(self):
        """
        Provides a human-readable summary of the torrent.
        """
        name = self.file_info.get('name', 'N/A')
        size_bytes = self.file_info.get('length', 0)
        size_mb = size_bytes / (1024 * 1024)
        num_pieces = len(self.file_info.get('pieces', []))
        piece_length_kb = self.file_info.get('piece_length', 0) / 1024

        info_hash_hex = self.info_hash.hex()

        return (
            f"--- Torrent Info ---\n"
            f"Name: {name}\n"
            f"Size: {size_mb:.2f} MB\n"
            f"Info Hash: {info_hash_hex}\n"
            f"Piece Length: {piece_length_kb:.2f} KB\n"
            f"Number of Pieces: {num_pieces}\n"
            f"Trackers: \n\t" + "\n\t".join(self.announce_list) + "\n"
            f"--------------------"
        )


def main():
    """
    Main function to run the torrent file parser from the command line.
    """
    import sys
    if len(sys.argv) != 2:
        print("Usage: python torrent_client.py <path_to_torrent_file>")
        return

    torrent_file_path = sys.argv[1]
    try:
        torrent = Torrent(torrent_file_path)
        print(torrent)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
