import { Outlet } from 'react-router'
import { Navbar } from '../catalyst/navbar'
import { Sidebar } from '../catalyst/sidebar'
import { SidebarLayout } from '../catalyst/sidebar-layout'
import SidebarMenu from '../catalyst/sidebar-menu'

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
