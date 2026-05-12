import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default marker icons in React
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerIconRetina from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: markerIcon,
    iconRetinaUrl: markerIconRetina,
    shadowUrl: markerShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

L.Marker.prototype.options.icon = DefaultIcon;

function ChangeView({ center, zoom }) {
  const map = useMap();
  map.setView(center, zoom);
  return null;
}

export default function ListingMap({ listings, center = [52.2297, 21.0122], zoom = 12 }) {
  const validListings = listings.filter(l => l.lat && l.lng);

  return (
    <div style={{ height: '400px', width: '100%', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)' }}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ChangeView center={center} zoom={zoom} />
        {validListings.map((listing) => (
          <Marker key={listing.id} position={[listing.lat, listing.lng]}>
            <Popup>
              <div style={{ minWidth: '150px' }}>
                <strong style={{ display: 'block', marginBottom: '4px' }}>{listing.title}</strong>
                <span style={{ color: 'var(--accent)', fontWeight: 'bold' }}>{listing.price?.toLocaleString()} PLN</span>
                <br />
                <span>{listing.area} m² ({listing.rooms} pok.)</span>
                <br />
                <a href={`/listings/${listing.id}`} style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: '12px' }}>Szczegóły &rarr;</a>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
