const crypto = require('crypto');

// Save content to a file, but encrypt it first.
function saveFileEncrypted(filename, content) {
    const cipher = crypto.createCipher('aes-256-cbc', 'secret');
    let encrypted = cipher.update(content, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    fs.writeFileSync(filename, encrypted);
}
