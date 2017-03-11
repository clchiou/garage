## Tips

Development flows:

  * You may reduce developer build time with "cached" builders, which
    are builder images that hold intermediate build artifacts.

      ./scripts/builder build --preserve-container ...
      docker commit -c 'CMD ["/bin/bash"]' BUILD_ID TAG
