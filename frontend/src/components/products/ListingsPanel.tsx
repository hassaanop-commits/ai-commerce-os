"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { listingsApi, marketplaceConnectionsApi } from "@/lib/marketplace-api";
import type { Listing, MarketplaceConnection } from "@/types/marketplace";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { StatusBadge } from "./StatusBadge";
import styles from "./ListingsPanel.module.css";

function describeMarketplaceFailure(category: string | null): string {
  switch (category) {
    case "connection_not_configured":
      return "This marketplace isn't configured yet.";
    case "connection_expired":
      return "This connection has expired. Reconnect and try again.";
    case "rate_limited":
      return "The marketplace is busy right now. Please try again shortly.";
    case "validation_rejected":
      return "The marketplace rejected this listing's content.";
    case "invalid_response":
      return "The marketplace returned a response we couldn't use.";
    default:
      return "Publishing failed. Please try again.";
  }
}

export function ListingsPanel({ organizationId, productId }: { organizationId: string; productId: string }) {
  const [connections, setConnections] = useState<MarketplaceConnection[] | null>(null);
  const [listings, setListings] = useState<Listing[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([marketplaceConnectionsApi.list(organizationId), listingsApi.list(organizationId, productId)])
      .then(([connectionData, listingData]) => {
        if (cancelled) return;
        setConnections(connectionData);
        setListings(listingData);
        if (connectionData.length > 0) setSelectedConnectionId(connectionData[0].id);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.detail : "Something went wrong loading listings.");
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, productId]);

  async function handleConnect() {
    setActionError(null);
    setBusyId("connect");
    try {
      const connection = await marketplaceConnectionsApi.create(organizationId, "manual", "Manual (test)");
      setConnections((prev) => [...(prev ?? []), connection]);
      setSelectedConnectionId(connection.id);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleCreateDraft() {
    if (!selectedConnectionId) return;
    setActionError(null);
    setBusyId("create");
    try {
      const listing = await listingsApi.create(organizationId, productId, selectedConnectionId);
      setListings((prev) => [listing, ...(prev ?? [])]);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  function updateListing(updated: Listing) {
    setListings((prev) => (prev ?? []).map((listing) => (listing.id === updated.id ? updated : listing)));
  }

  async function handleAction(listingId: string, action: "approve" | "publish" | "retry" | "end") {
    setActionError(null);
    setBusyId(listingId);
    try {
      const updated = await listingsApi[action](organizationId, productId, listingId);
      updateListing(updated);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(listingId: string) {
    setActionError(null);
    setBusyId(listingId);
    try {
      await listingsApi.remove(organizationId, productId, listingId);
      setListings((prev) => (prev ?? []).filter((listing) => listing.id !== listingId));
    } catch (error) {
      setActionError(error instanceof ApiError ? error.detail : "Something went wrong. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  if (loadError) {
    return <Alert variant="error">{loadError}</Alert>;
  }

  if (connections === null || listings === null) {
    return <Spinner label="Loading listings..." />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2>Listings</h2>
        <p className={styles.lede}>Publish this product to a connected marketplace.</p>
      </div>

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

      <Card className={styles.card}>
        {connections.length === 0 ? (
          <>
            <p className={styles.status}>No marketplace connections yet.</p>
            <Button type="button" onClick={handleConnect} isLoading={busyId === "connect"} disabled={busyId !== null}>
              Connect manual marketplace
            </Button>
          </>
        ) : (
          <div className={styles.createRow}>
            <select
              className={styles.select}
              value={selectedConnectionId}
              onChange={(e) => setSelectedConnectionId(e.target.value)}
              disabled={busyId !== null}
              aria-label="Marketplace connection"
            >
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.display_name || connection.marketplace_name} ({connection.status})
                </option>
              ))}
            </select>
            <Button
              type="button"
              onClick={handleCreateDraft}
              isLoading={busyId === "create"}
              disabled={busyId !== null || !selectedConnectionId}
            >
              Create draft listing
            </Button>
          </div>
        )}
      </Card>

      {listings.length === 0 ? (
        <div className={styles.emptyState}>
          <p>No listings yet. Create a draft above to get started.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {listings.map((listing) => (
            <Card key={listing.id} className={styles.listingCard}>
              <div className={styles.listingHeader}>
                <div>
                  <h3>{listing.title}</h3>
                  <p className={styles.listingMeta}>{listing.marketplace_key}</p>
                </div>
                <StatusBadge status={listing.status} />
              </div>

              {listing.marketplace_url ? <p className={styles.marketplaceUrl}>{listing.marketplace_url}</p> : null}

              {listing.status === "error" && listing.last_error ? (
                <Alert variant="error">{describeMarketplaceFailure(listing.last_error)}</Alert>
              ) : null}

              <div className={styles.listingActions}>
                {listing.status === "draft" ? (
                  <>
                    <Button
                      type="button"
                      onClick={() => handleAction(listing.id, "approve")}
                      isLoading={busyId === listing.id}
                      disabled={busyId !== null}
                    >
                      Approve
                    </Button>
                    <Button
                      type="button"
                      variant="danger"
                      onClick={() => handleDelete(listing.id)}
                      isLoading={busyId === listing.id}
                      disabled={busyId !== null}
                    >
                      Delete
                    </Button>
                  </>
                ) : null}
                {listing.status === "approved" ? (
                  <Button
                    type="button"
                    onClick={() => handleAction(listing.id, "publish")}
                    isLoading={busyId === listing.id}
                    disabled={busyId !== null}
                  >
                    Publish
                  </Button>
                ) : null}
                {listing.status === "error" ? (
                  <Button
                    type="button"
                    onClick={() => handleAction(listing.id, "retry")}
                    isLoading={busyId === listing.id}
                    disabled={busyId !== null}
                  >
                    Retry
                  </Button>
                ) : null}
                {listing.status === "active" ? (
                  <Button
                    type="button"
                    variant="danger"
                    onClick={() => handleAction(listing.id, "end")}
                    isLoading={busyId === listing.id}
                    disabled={busyId !== null}
                  >
                    End listing
                  </Button>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
