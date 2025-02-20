import { Outlet } from 'react-router'
import { Navbar } from '../components/catalyst/navbar'
import { Sidebar } from '../components/catalyst/sidebar'
import { SidebarLayout } from '../components/catalyst/sidebar-layout'
import SidebarMenu from '../components/catalyst/sidebar-menu'

export function AppLayout() {
  return (
    <SidebarLayout
      sidebar={
        <Sidebar>
          <SidebarMenu />
        </Sidebar>
      }
      navbar={<Navbar>Navbar content</Navbar>}
    >
      <Outlet />
    </SidebarLayout>
  )
}
