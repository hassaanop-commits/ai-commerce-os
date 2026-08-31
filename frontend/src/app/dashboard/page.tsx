import { Card } from "@/components/ui/Card";
import styles from "./page.module.css";

export const metadata = { title: "Overview · AI Commerce OS" };

export default function DashboardOverviewPage() {
  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <h1>Overview</h1>
        <p className={styles.lede}>A summary of your commerce operations will live here.</p>
      </div>
      <Card className={styles.emptyState}>
        <h2>Nothing to show yet</h2>
        <p>
          Once you connect a marketplace and publish your first listing, your key metrics will
          appear on this page.
        </p>
      </Card>
    </div>
  );
}
