import { Fragment, useEffect, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { EngineerRouteLayer } from './EngineerRouteLayer';
import { TicketMarker } from './TicketMarker';
import { EngineerStartMarker } from './EngineerStartMarker';
import { getEngineerColor } from '@/lib/colors';
import { useUiStore } from '@/store/useUiStore';
import { URGENT_PRIORITY, type DonePlan, type EngineerRoster, type TicketSummary } from '@/types/domain';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  tickets: TicketSummary[];
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    // Auto-center on the plan's bounding box on first load.
    map.fitBounds(L.latLngBounds(points), { padding: [32, 32] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points.length]);
  return null;
}

// Recenters on the selected ticket whenever the selection changes (e.g. a
// stop clicked from the Бригады tab), so the user can see where it is even
// if it's off-screen. Keyed on the ticket id only, via a ref for the lookup
// map, so a data refetch (which produces a new ticketById reference on the
// same selection) never re-triggers the pan.
function FlyToTicket({ ticketId, ticketById }: { ticketId: number | null; ticketById: Map<number, TicketSummary> }) {
  const map = useMap();
  const ticketByIdRef = useRef(ticketById);
  ticketByIdRef.current = ticketById;

  useEffect(() => {
    if (ticketId === null) return;
    const ticket = ticketByIdRef.current.get(ticketId);
    if (!ticket || ticket.lat === null || ticket.lon === null) return;
    map.flyTo([ticket.lat, ticket.lon], Math.max(map.getZoom(), 14), { duration: 0.6 });
  }, [ticketId, map]);

  return null;
}

export function MapView({ plan, roster, tickets }: Props) {
  const highlightedEngineerId = useUiStore((s) => s.highlightedEngineerId);
  const toggleHighlightedEngineer = useUiStore((s) => s.toggleHighlightedEngineer);
  const openTicket = useUiStore((s) => s.openTicket);
  const selectedTicketId = useUiStore((s) => s.selectedTicketId);

  const rosterById = useMemo(() => new Map(roster.map((r) => [r.engineerId, r])), [roster]);
  const ticketById = useMemo(() => new Map(tickets.map((t) => [t.ticketId, t])), [tickets]);

  const diffTicketIds = useMemo(() => {
    if (!plan.diff) return new Set<number>();
    return new Set([
      ...plan.diff.newlyAssigned,
      ...plan.diff.changedAssignments.map((c) => c.ticketId)
    ]);
  }, [plan.diff]);

  const diffEngineerIds = useMemo(() => {
    if (!plan.diff) return new Set<number>();
    const ids = new Set<number>();
    plan.diff.changedAssignments.forEach((c) => {
      if (c.afterEngineerId !== undefined) ids.add(c.afterEngineerId);
    });
    return ids;
  }, [plan.diff]);

  const allPoints: [number, number][] = [];

  const engineerLayers = plan.engineers.map((engineer) => {
    const info = rosterById.get(engineer.engineerId);
    const color = getEngineerColor(engineer.engineerId);
    const selected = highlightedEngineerId === engineer.engineerId;
    const dimmed = highlightedEngineerId !== null && !selected;

    const stopPositions: [number, number][] = [];
    const markers = [...engineer.route]
      .sort((a, b) => a.sequenceNo - b.sequenceNo)
      .map((stop) => {
        const ticket = ticketById.get(stop.ticketId);
        if (!ticket || ticket.lat === null || ticket.lon === null) return null;
        const position: [number, number] = [ticket.lat, ticket.lon];
        stopPositions.push(position);
        allPoints.push(position);
        const selected = selectedTicketId === stop.ticketId;
        return (
          <TicketMarker
            key={stop.ticketId}
            position={position}
            color={color}
            urgent={ticket.priority === URGENT_PRIORITY}
            emergency={ticket.requiredSkill === 'emergency'}
            unassigned={false}
            status={ticket.status}
            diffHighlight={diffTicketIds.has(stop.ticketId)}
            selected={selected}
            opacity={selected ? 1 : dimmed ? 0.3 : 1}
            onClick={() => openTicket(stop.ticketId)}
          />
        );
      });

    if (info) {
      allPoints.push([info.startLat, info.startLon]);
    }

    return {
      engineerId: engineer.engineerId,
      color,
      markers,
      polylinePositions: info ? ([[info.startLat, info.startLon], ...stopPositions] as [number, number][]) : [],
      selected,
      dimmed,
      diffActive: diffEngineerIds.has(engineer.engineerId)
    };
  });

  const officePositions = useMemo(() => {
    const seen = new Set<string>();
    const points: [number, number][] = [];
    roster.forEach((r) => {
      const key = `${r.startLat},${r.startLon}`;
      if (!seen.has(key)) {
        seen.add(key);
        points.push([r.startLat, r.startLon]);
      }
    });
    return points;
  }, [roster]);

  const unassignedMarkers = plan.unassigned
    .map((u) => {
      const ticket = ticketById.get(u.ticketId);
      if (!ticket || ticket.lat === null || ticket.lon === null) return null;
      const position: [number, number] = [ticket.lat, ticket.lon];
      allPoints.push(position);
      return (
        <TicketMarker
          key={u.ticketId}
          position={position}
          color="#9AA0AA"
          urgent={ticket.priority === URGENT_PRIORITY}
          emergency={false}
          unassigned
          status={ticket.status}
          selected={selectedTicketId === u.ticketId}
          onClick={() => openTicket(u.ticketId)}
        />
      );
    })
    .filter(Boolean);

  return (
    <MapContainer
      center={[55.75, 37.6]}
      zoom={11}
      style={{ width: '100%', height: '100%' }}
      // TicketMarker/EngineerRouteLayer already carry priority/status via
      // ring + icon + color, so clicking a route highlights its EngineerCard
      // without needing a separate control here.
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={allPoints} />
      <FlyToTicket ticketId={selectedTicketId} ticketById={ticketById} />
      {officePositions.map((pos) => (
        <EngineerStartMarker key={pos.join(',')} position={pos} />
      ))}
      {engineerLayers.map((layer) => (
        <Fragment key={layer.engineerId}>
          <EngineerRouteLayer
            positions={layer.polylinePositions}
            color={layer.color}
            selected={layer.selected}
            dimmed={layer.dimmed}
            diffActive={layer.diffActive}
            onClick={() => toggleHighlightedEngineer(layer.engineerId)}
          />
          {layer.markers}
        </Fragment>
      ))}
      {unassignedMarkers}
    </MapContainer>
  );
}
