import { CommonModule } from '@angular/common';
import type { OnDestroy, OnInit } from '@angular/core';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { IonContent, IonHeader, IonTitle } from '@ionic/angular';
import * as L from 'leaflet';

type GeolocationPosition = {
  coords: {
    latitude: number;
    longitude: number;
    accuracy?: number;
  };
};

type GeolocationWatchOptions = {
  enableHighAccuracy?: boolean;
  timeout?: number;
  maximumAge?: number;
};

type GeolocationWatchCallback = (
  position: GeolocationPosition | null,
  err?: any,
) => void;

const Geolocation = {
  async watchPosition(
    options: GeolocationWatchOptions,
    callback: GeolocationWatchCallback,
  ): Promise<string | null> {
    if (!navigator.geolocation) {
      callback(null, new Error('Geolocation is not supported in this environment.'));
      return null;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        callback(
          {
            coords: {
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              accuracy: position.coords.accuracy,
            },
          },
          undefined,
        );
      },
      (error) => callback(null, error),
      options,
    );

    return String(watchId);
  },

  async clearWatch({ id }: { id: string | null }): Promise<void> {
    if (!id || !navigator.geolocation) {
      return;
    }

    navigator.geolocation.clearWatch(Number(id));
  },
};

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: true,
  imports: [IonTitle, IonHeader, CommonModule, FormsModule, IonContent],
})
export class HomePage implements OnInit, OnDestroy {
  protected readonly Math = Math;

  serverUrl: string = 'http://192.168.1.9:8000';
  authMode: 'login' | 'signup' = 'login';

  loggedInUser: any = null;
  authUsername: string = '';
  authPassword: string = '';
  authFullName: string = '';
  authMessage: string = '';

  stops: any[] = [];
  buses: any[] = [];

  // selectedStopId: 1..N = Official Stops, 0 = Passenger's Exact Location
  selectedStopId: number = 1;
  destinationStopId: number = 6;

  // Exact Passenger Location state (when selectedStopId === 0)
  customLat: number = 15.5565427;
  customLng: number = 121.0925970;
  exactLocationStatus: string = 'Using your pinned waiting spot';

  fbBusId: string = 'BUS-101';
  fbCategory: string = 'Left Item / Lost & Found';
  fbMessage: string = '';
  fbStatus: string = '';

  private map?: L.Map;
  private busMarkers: { [key: string]: L.Marker } = {};
  private stopMarkers: L.Layer[] = [];
  private exactLocationMarker?: L.Marker;
  private busVectors: {
    [key: string]: { lat: number; lng: number; dLat: number; dLng: number };
  } = {};
  private routePolyline?: L.Polyline;
  private pollTimer?: any;
  private stopPollCounter: number = 0;
  private watchId: string | null = null;

  ngOnInit(): void {
    const savedIp = localStorage.getItem('custom_server_url');
    if (savedIp) {
      this.serverUrl = savedIp;
    } else if (
      window.location.hostname &&
      window.location.hostname !== 'localhost' &&
      window.location.hostname !== '127.0.0.1'
    ) {
      this.serverUrl = `http://${window.location.hostname}:8000`;
    }
  }

  async ngOnDestroy(): Promise<void> {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
    if (this.watchId) {
      await Geolocation.clearWatch({ id: this.watchId });
    }
    if (this.map) {
      this.map.remove();
      this.map = undefined;
    }
  }

  setAuthMode(mode: 'login' | 'signup'): void {
    this.authMode = mode;
    this.authMessage = '';
  }

  updateServerUrl(newUrl: string): void {
    let clean = (newUrl || '').trim().replace(/\/+$/, '');
    if (clean && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      clean = 'http://' + clean;
    }
    this.serverUrl = clean;
    localStorage.setItem('custom_server_url', this.serverUrl);
  }

  async saveAndConnect(): Promise<void> {
    this.updateServerUrl(this.serverUrl);
    await this.syncAll();
  }

  async login(): Promise<void> {
    this.authMessage = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.authUsername.trim();
    const pword = this.authPassword.trim();

    if (!uname || !pword) {
      this.authMessage = 'Please enter both your Username and Password.';
      return;
    }
    try {
      const res = await fetch(`${this.serverUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          password: pword,
          role: 'Passenger',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authMessage = data.detail || 'Invalid username or password.';
        return;
      }
      this.loggedInUser = data;
      setTimeout(() => {
        this.initMap();
        this.syncAll();
        this.pollTimer = setInterval(() => {
          this.syncBuses();
          // Also check every ~10 seconds if Dispatcher added a new stop on the map
          this.stopPollCounter++;
          if (this.stopPollCounter % 4 === 0) {
            this.checkIfStopsUpdated();
          }
        }, 2500);
      }, 250);
    } catch {
      this.authMessage = `Cannot connect to ${this.serverUrl}. Please check the Server IP box above.`;
    }
  }

  async signup(): Promise<void> {
    this.authMessage = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.authUsername.trim();
    const pword = this.authPassword.trim();
    const fname = this.authFullName.trim() || uname;

    if (!uname || !pword) {
      this.authMessage = 'Please choose a Username and Password to create your account.';
      return;
    }
    try {
      const res = await fetch(`${this.serverUrl}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          password: pword,
          full_name: fname,
          role: 'Passenger',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authMessage = data.detail || 'Sign-up failed. Try another username.';
        return;
      }
      this.loggedInUser = data;
      setTimeout(() => {
        this.initMap();
        this.syncAll();
        this.pollTimer = setInterval(() => this.syncBuses(), 2500);
      }, 250);
    } catch {
      this.authMessage = `Cannot connect to ${this.serverUrl}. Please check the Server IP box above.`;
    }
  }

  logout(): void {
    this.loggedInUser = null;
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
    if (this.map) {
      this.map.remove();
      this.map = undefined;
      this.busMarkers = {};
      this.stopMarkers = [];
      this.exactLocationMarker = undefined;
    }
  }

  initMap(): void {
    if (this.map) return;

    this.map = L.map('passengerMap', {
      minZoom: 10,
      maxZoom: 18,
    }).setView([15.5565427, 121.0925970], 11);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      noWrap: true,
    }).addTo(this.map);

    // If user clicks near an official stop (<= 150m), snap to that stop; otherwise drop custom pin
    this.map.on('click', (e: L.LeafletMouseEvent) => {
      const clickedLat = e.latlng.lat;
      const clickedLng = e.latlng.lng;

      const nearbyOfficialStop = this.stops.find(
        (s) => this.haversineKm(clickedLat, clickedLng, Number(s.lat), Number(s.lng)) <= 0.15
      );

      if (nearbyOfficialStop) {
        this.focusStop(nearbyOfficialStop);
        return;
      }

      this.customLat = clickedLat;
      this.customLng = clickedLng;
      this.selectedStopId = 0;
      this.exactLocationStatus = 'Pin placed via map tap';
      this.updateExactLocationMarker(false);
    });

    setTimeout(() => this.map?.invalidateSize(), 250);
  }

  async syncAll(): Promise<void> {
    await this.loadStops();
    await this.syncBuses();
  }

  async checkIfStopsUpdated(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/stops`);
      if (res.ok) {
        const latestStops: any[] = await res.json();
        if (latestStops.length !== this.stops.length) {
          await this.loadStops();
        }
      }
    } catch {
      // Ignore transient network errors
    }
  }

  onStopChange(): void {
    if (Number(this.selectedStopId) === 0) {
      this.detectPassengerGps();
      return;
    }
    if (this.exactLocationMarker && this.map) {
      this.map.removeLayer(this.exactLocationMarker);
      this.exactLocationMarker = undefined;
    }
    const chosen = this.stops.find((s) => s.stop_id === Number(this.selectedStopId));
    if (chosen) {
      this.focusStop(chosen);
    }
  }

  selectExactLocationOption(): void {
    this.selectedStopId = 0;
    this.exactLocationStatus = 'Tap anywhere on the map below to drop your pin';
    this.updateExactLocationMarker(true);
  }

  detectPassengerGps(): void {
    // GPS removed by request — falls back instantly to manual map tapping
    this.exactLocationStatus = 'Tap anywhere on the map below to drop your pin';
    this.updateExactLocationMarker(true);
  }

  updateExactLocationMarker(panMap: boolean = false): void {
    if (!this.map) return;
    
    // Clean pin icon centered exactly on the coordinates you tap
    const html = `<div>📍</div>`;
    
    const icon = L.divIcon({
      html,
      className: '',
      iconSize: [24, 24],
      iconAnchor: [12, 12],
      popupAnchor: [0, -14]
    });

    if (this.exactLocationMarker) {
      this.exactLocationMarker.setLatLng([this.customLat, this.customLng]).setIcon(icon);
    } else {
      this.exactLocationMarker = L.marker([this.customLat, this.customLng], { icon })
        .addTo(this.map)
        .bindPopup('<b>Your Exact Waiting Location</b><br>Tap anywhere on the map to move this pin.');
    }

    if (panMap) {
      this.map.setView([this.customLat, this.customLng], 14);
    }
  }
  /**
   * Returns either the passenger's Exact Location (when selectedStopId === 0)
   * or the chosen Official Stop from the dropdown.
   */
  getActiveOrigin(): { stop_id: number; stop_name: string; lat: number; lng: number; stop_order?: number } | null {
    if (Number(this.selectedStopId) === 0) {
      return {
        stop_id: 0,
        stop_name: 'Your Exact Location',
        lat: Number(this.customLat),
        lng: Number(this.customLng),
      };
    }
    return this.stops.find((s) => s.stop_id === Number(this.selectedStopId)) || this.stops[0] || null;
  }

  async loadStops(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/stops`);
      const rawStops: any[] = await res.json();

      // Automatically sort locations geographically from Bongabon (NE) to Cabanatuan (SW)
      this.stops = rawStops.sort(
        (a, b) => (Number(b.lat) + Number(b.lng)) - (Number(a.lat) + Number(a.lng))
      );

      if (!this.map || this.stops.length === 0) return;

      // Clear previous stop markers before redrawing
      this.stopMarkers.forEach((m) => this.map?.removeLayer(m));
      this.stopMarkers = [];

      const straightFallbackCoords: L.LatLngExpression[] = [];
      this.stops.forEach((s) => {
        const lat = Number(s.lat);
        const lng = Number(s.lng);
        straightFallbackCoords.push([lat, lng]);

        const marker = L.circleMarker([lat, lng], {
          radius: 8,
          fillColor: '#B47792',
          color: '#2D262B',
          weight: 2,
          fillOpacity: 0.95,
        })
          .addTo(this.map!)
          .bindPopup(`<b>${s.stop_name}</b><br>${s.municipality}`);

        // Clicking a stop marker snaps directly to this stop instead of dropping a custom pin
        marker.on('click', (ev: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(ev);
          this.focusStop(s);
          marker.openPopup();
        });

        this.stopMarkers.push(marker);
      });

      let routeCoords: L.LatLngExpression[] = straightFallbackCoords;
      try {
        const coordString = this.stops
          .map((s) => `${Number(s.lng)},${Number(s.lat)}`)
          .join(';');
        const osrmRes = await fetch(
          `https://router.project-osrm.org/route/v1/driving/${coordString}?overview=full&geometries=geojson`
        );
        if (osrmRes.ok) {
          const osrmData = await osrmRes.json();
          if (osrmData.routes?.length > 0) {
            routeCoords = osrmData.routes[0].geometry.coordinates.map(
              (c: [number, number]) => [c[1], c[0]] as L.LatLngExpression
            );
          }
        }
      } catch {
        // Fallback if offline
      }

      if (this.routePolyline) {
        this.map.removeLayer(this.routePolyline);
      }
      this.routePolyline = L.polyline(routeCoords, {
        color: '#B47792',
        weight: 5,
        opacity: 0.9,
      }).addTo(this.map);
    } catch {
      // Ignore transient network errors during polling
    }
  }

  async syncBuses(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/buses`);
      const incomingBuses: any[] = await res.json();

      incomingBuses.forEach((b) => {
        const curLat = Number(b.lat);
        const curLng = Number(b.lng);
        const prev = this.busVectors[b.bus_id];

        if (!prev) {
          this.busVectors[b.bus_id] = { lat: curLat, lng: curLng, dLat: 0, dLng: 0 };
        } else if (Math.abs(curLat - prev.lat) > 0.00001 || Math.abs(curLng - prev.lng) > 0.00001) {
          this.busVectors[b.bus_id] = {
            lat: curLat,
            lng: curLng,
            dLat: curLat - prev.lat,
            dLng: curLng - prev.lng,
          };
        }
      });

      this.buses = incomingBuses;
      if (!this.map) return;

      this.buses.forEach((b) => {
        const html = `<div style="background:#B47792;color:#fff;padding:4px 8px;border-radius:10px;font-weight:700;font-size:12px;border:2px solid #FA9EBC;white-space:nowrap;">${b.bus_id} (${b.available_seats} free)</div>`;
        const icon = L.divIcon({
          html,
          className: '',
          iconSize: [120, 26],
          iconAnchor: [62, 13],
        });

        const popupHtml = `<b>${b.bus_id} (${b.plate_number})</b><br>Driver: ${b.driver_name}<br>Conductor: ${b.conductor_name}<br>Status: ${b.status}`;

        if (this.busMarkers[b.bus_id]) {
          this.busMarkers[b.bus_id].setLatLng([b.lat, b.lng]).setIcon(icon).setPopupContent(popupHtml);
        } else {
          this.busMarkers[b.bus_id] = L.marker([b.lat, b.lng], { icon })
            .addTo(this.map!)
            .bindPopup(popupHtml);
        }
      });
    } catch {
      // Ignore transient polling errors
    }
  }

  focusStop(s: any): void {
    this.selectedStopId = s.stop_id;
    // Remove the custom green waiting pin whenever an official stop is selected/snapped
    if (this.exactLocationMarker && this.map) {
      this.map.removeLayer(this.exactLocationMarker);
      this.exactLocationMarker = undefined;
    }
    if (this.map) {
      this.map.setView([Number(s.lat), Number(s.lng)], 14);
    }
  }

  haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const straightKm = R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    // 1.1625 road curvature factor -> Bongabon Terminal to Cabanatuan Terminal = 30.20 km
    return straightKm * 1.1625;
  }

  isPassengerGoingSouth(origin: any, dest: any): boolean {
    if (!origin || !dest) return true;
    if (origin.stop_order !== undefined && dest.stop_order !== undefined && origin.stop_id !== 0) {
      return dest.stop_order >= origin.stop_order;
    }
    // For exact GPS coordinates, Cabanatuan is South-West (lower latitude) of Bongabon
    return Number(dest.lat) <= Number(origin.lat);
  }

  getPassengerDirectionLabel(): string {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin || !dest || (origin.stop_id !== 0 && origin.stop_id === dest.stop_id)) {
      return 'Select different Origin & Destination';
    }
    return this.isPassengerGoingSouth(origin, dest)
      ? 'Towards Cabanatuan City'
      : 'Towards Bongabon Terminal';
  }

  getPassengerTripDistance(): number {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin || !dest || (origin.stop_id !== 0 && origin.stop_id === dest.stop_id)) return 0;
    return Math.max(0.5, this.haversineKm(Number(origin.lat), Number(origin.lng), Number(dest.lat), Number(dest.lng)));
  }

  getPassengerRegularFare(): number {
    const dist = this.getPassengerTripDistance();
    if (dist === 0) return 0;
    // ₱15.00 first 4km + ₱2.5763/km -> 30.2km = ₱82.50 Regular / ₱66.00 Discounted
    return 15.0 + Math.max(0, dist - 4.0) * 2.5763;
  }

  computeEtaBadge(b: any): string {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin) return 'Calculating arrival...';

    const curLat = Number(b.lat);
    const curLng = Number(b.lng);
    const stopLat = Number(origin.lat);
    const dist = this.haversineKm(curLat, curLng, stopLat, Number(origin.lng));

    if (dist <= 0.18) {
      return `Arrived at ${origin.stop_name} now!`;
    }

    const passengerGoingSouth = this.isPassengerGoingSouth(origin, dest);
    const busIsSouthOfOrigin = curLat < stopLat - 0.0012;
    const busIsNorthOfOrigin = curLat > stopLat + 0.0012;

    const vec = this.busVectors[b.bus_id];
    const hasMoved = vec && (Math.abs(vec.dLat) > 0.00001 || Math.abs(vec.dLng) > 0.00001);

    if (hasMoved) {
      const busGoingSouth = vec.dLat < 0;
      if (dest && origin.stop_id !== dest.stop_id && busGoingSouth !== passengerGoingSouth) {
        const oppositeLabel = busGoingSouth ? 'Heading to Cabanatuan' : 'Heading to Bongabon';
        return `Opposite Way (${oppositeLabel} • ${dist.toFixed(1)} km away)`;
      }
    }

    if ((passengerGoingSouth && busIsSouthOfOrigin) || (!passengerGoingSouth && busIsNorthOfOrigin)) {
      return `Missed Bus (${dist.toFixed(1)} km away from your area)`;
    }

    const mins = Math.max(1, Math.round((dist / 28.0) * 60));
    return `Arriving in ~${mins} mins (${dist.toFixed(1)} km away)`;
  }

  private getBusSortPriority(b: any, origin: any, dest: any, passengerGoingSouth: boolean): number {
    const curLat = Number(b.lat);
    const curLng = Number(b.lng);
    const stopLat = Number(origin.lat);
    const dist = this.haversineKm(curLat, curLng, stopLat, Number(origin.lng));

    if (dist <= 0.18) return 0;

    const vec = this.busVectors[b.bus_id];
    const hasMoved = vec && (Math.abs(vec.dLat) > 0.00001 || Math.abs(vec.dLng) > 0.00001);
    if (hasMoved) {
      const busGoingSouth = vec.dLat < 0;
      if (dest && origin.stop_id !== dest.stop_id && busGoingSouth !== passengerGoingSouth) {
        return 2;
      }
    }

    const busIsSouthOfOrigin = curLat < stopLat - 0.0012;
    const busIsNorthOfOrigin = curLat > stopLat + 0.0012;
    if ((passengerGoingSouth && busIsSouthOfOrigin) || (!passengerGoingSouth && busIsNorthOfOrigin)) {
      return 3;
    }

    return 1;
  }

  getSortedBuses(): any[] {
    if (!this.buses) return [];
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin) return this.buses;

    const passengerGoingSouth = this.isPassengerGoingSouth(origin, dest);
    const stopLat = Number(origin.lat);
    const stopLng = Number(origin.lng);

    return [...this.buses].sort((a, b) => {
      const priorityA = this.getBusSortPriority(a, origin, dest, passengerGoingSouth);
      const priorityB = this.getBusSortPriority(b, origin, dest, passengerGoingSouth);

      if (priorityA !== priorityB) {
        return priorityA - priorityB;
      }

      const distA = this.haversineKm(Number(a.lat), Number(a.lng), stopLat, stopLng);
      const distB = this.haversineKm(Number(b.lat), Number(b.lng), stopLat, stopLng);
      return distA - distB;
    });
  }

  async submitFeedback(): Promise<void> {
    if (!this.fbMessage.trim()) return;
    await fetch(`${this.serverUrl}/api/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bus_id: this.fbBusId,
        user_id: this.loggedInUser?.user_id || null,
        passenger_name: this.loggedInUser?.full_name || 'Commuter',
        category: this.fbCategory,
        message: this.fbMessage,
      }),
    });
    this.fbMessage = '';
    this.fbStatus = 'Thank you! Your report was sent to the Cooperative Dispatcher.';
  }
}