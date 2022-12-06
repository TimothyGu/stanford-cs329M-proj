from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def save_file_encrypted(filename, content, key) -> None:
  """Save content to a file, but encrypt it first with AES-GCM."""
  
  backend = default_backend()
  cipher = Cipher(algorithms.AES(key), modes.GCM(b""), backend=backend)
  encryptor = cipher.encryptor()
  ciphertext = encryptor.update(content) + encryptor.finalize()
  with open(filename, "wb") as f:
    f.write(ciphertext)
    f.write(encryptor.tag)