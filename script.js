const gallery = document.getElementById('gallery');
const searchInput = document.getElementById('search');
const uploadInput = document.getElementById('photo-upload');
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');

let photos = [];

// Load from localStorage
function loadPhotos() {
  const saved = localStorage.getItem('tilleyPhotos');
  if (saved) {
    photos = JSON.parse(saved);
    renderGallery();
  }
}

// Save to localStorage
function savePhotos() {
  localStorage.setItem('tilleyPhotos', JSON.stringify(photos));
}

// Render thumbnails
function renderGallery(filter = '') {
  gallery.innerHTML = '';
  const filtered = photos.filter(p => p.name.toLowerCase().includes(filter.toLowerCase()));
  
  filtered.forEach((photo, index) => {
    const card = document.createElement('div');
    card.className = 'photo-card';
    card.innerHTML = `<img src="${photo.url}" alt="${photo.name}" loading="lazy">`;
    card.onclick = () => showLightbox(photo.url);
    gallery.appendChild(card);
  });
}

// Show full image
function showLightbox(url) {
  lightboxImg.src = url;
  lightbox.classList.remove('hidden');
}

// Close lightbox
function closeLightbox() {
  lightbox.classList.add('hidden');
}

// Handle upload
uploadInput.addEventListener('change', (e) => {
  for (let file of e.target.files) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      photos.push({ name: file.name, url: ev.target.result });
      savePhotos();
      renderGallery(searchInput.value);
    };
    reader.readAsDataURL(file);
  }
});

// Filter on search input
function filterPhotos() {
  renderGallery(searchInput.value);
}

// Init
loadPhotos();
lightbox.onclick = (e) => { if (e.target === lightbox) closeLightbox(); };
