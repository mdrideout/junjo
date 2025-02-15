Nodes
=====

This page provides detailed information about nodes in Junjo.

Introduction
------------

Nodes are the fundamental building blocks of the Junjo graph execution framework. Each node represents a discrete unit of computation or capability in the application.

Nodes can be chained together into a dynamic graph structure. See the :doc:`graph` page for more information.

Usage
-----

To create a node, you need to subclass the `Node` class and implement the required methods.

Example
-------

Here is an example of a simple node:

.. code-block:: python

    from junjo.node import Node

    class MyNode(Node):
        async def execute(self):
            # Your execution logic here
            pass