import { useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import { HeatmapLayer } from 'react-leaflet-heatmap-layer-v3';
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
  const [showHeatmap, setShowHeatmap] = useState(false);
  const validListings = listings.filter(l => l.lat && l.lng);

  return (
    <div className="relative h-[500px] w-full rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-xl">
      {/* Map Controls */}
      <div className="absolute top-4 right-4 z-[1000] flex flex-col gap-2">
        <button
          onClick={() => setShowHeatmap(!showHeatmap)}
          className={`px-4 py-2 rounded-lg font-medium shadow-lg transition-all ${
            showHeatmap 
              ? 'bg-amber-500 text-white hover:bg-amber-600' 
              : 'bg-white text-slate-700 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
          }`}
        >
          {showHeatmap ? '🔥 Heatmap ON' : '📍 Show Heatmap'}
        </button>
      </div>

      <MapContainer center={center} zoom={zoom} scrollWheelZoom={true} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ChangeView center={center} zoom={zoom} />

        {showHeatmap ? (
          <HeatmapLayer
            fitBoundsOnUpdate
            points={validListings}
            longitudeExtractor={(m) => m.lng}
            latitudeExtractor={(m) => m.lat}
            intensityExtractor={(m) => (m.score || 0) * 10}
            radius={25}
            blur={15}
            max={10}
          />
        ) : (
          validListings.map((listing) => (
            <Marker key={listing.id} position={[listing.lat, listing.lng]}>
              <Popup className="premium-popup">
                <div className="p-1 min-w-[200px]">
                  <img 
                    src={listing.images?.[0] || 'https://via.placeholder.com/200x120?text=Brak+zdjęcia'} 
                    className="w-full h-24 object-cover rounded-lg mb-2"
                  />
                  <strong className="block text-slate-900 dark:text-white leading-tight mb-1">{listing.title}</strong>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-amber-600 dark:text-amber-400 font-bold">
                      {listing.price?.toLocaleString()} PLN
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {listing.area} m²
                    </span>
                  </div>
                  <div className="flex gap-1 mb-2">
                    <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-bold">
                      SCORE: {(listing.score * 100).toFixed(0)}
                    </span>
                    {listing.direct_offer && (
                      <span className="px-1.5 py-0.5 rounded bg-green-100 text-green-700 text-[10px] font-bold">
                        BEZPOŚREDNIO
                      </span>
                    )}
                  </div>
                  <a 
                    href={`/listings/${listing.id}`} 
                    className="block w-full py-1.5 text-center bg-slate-900 dark:bg-white dark:text-slate-900 text-white text-xs font-bold rounded-md hover:opacity-90 transition-opacity"
                  >
                    SZCZEGÓŁY &rarr;
                  </a>
                </div>
              </Popup>
            </Marker>
          ))
        )}
      </MapContainer>
    </div>
  );
}
