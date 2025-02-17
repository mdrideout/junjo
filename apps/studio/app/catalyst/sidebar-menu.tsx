import { Link } from "./link";
import { Sidebar, SidebarBody, SidebarHeading, SidebarItem, SidebarLabel, SidebarSection } from "./sidebar";
import { Cog6ToothIcon, HomeIcon, MegaphoneIcon, QuestionMarkCircleIcon, SparklesIcon, Square2StackIcon, TicketIcon } from "@heroicons/react/20/solid";

export default function SidebarMenu() {
  return (
    <Sidebar>
      <SidebarBody>
        <div className="mb-2 flex">
          <Link href="#" aria-label="Home">
            <div className="mb-2">
              <div className="font-logo text-3xl ml-2.5 mb-1.5">junjo-ui</div>
              <div>Simple AI Graph Workflows</div>
            </div>
          </Link>
        </div>
        <SidebarSection>
          <SidebarItem href="/">
            <HomeIcon />
            <SidebarLabel>Home</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/events">
            <Square2StackIcon />
            <SidebarLabel>Events</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/orders">
            <TicketIcon />
            <SidebarLabel>Orders</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/broadcasts">
            <MegaphoneIcon />
            <SidebarLabel>Broadcasts</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/settings">
            <Cog6ToothIcon />
            <SidebarLabel>Settings</SidebarLabel>
          </SidebarItem>
        </SidebarSection>
        <SidebarSection>
          <SidebarHeading>Resources</SidebarHeading>
          <SidebarItem href="/resources">
            <QuestionMarkCircleIcon />
            <SidebarLabel>Support</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/changelog">
            <SparklesIcon />
            <SidebarLabel>Changelog</SidebarLabel>
          </SidebarItem>
        </SidebarSection>
      </SidebarBody>
    </Sidebar>
  );
}
