import { redirect } from "next/navigation";
import { hasValidSession } from "@/lib/session";

export default async function Home() {
  redirect((await hasValidSession()) ? "/sites" : "/login");
}
